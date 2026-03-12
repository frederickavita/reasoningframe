import httpx
from bs4 import BeautifulSoup
import re
import urllib.parse
from urllib import robotparser
import random
import time
from fake_useragent import UserAgent
from langdetect import detect, LangDetectException
from applications.reasoningframe.modules.contact_extractor import ContactExtractor

# ==========================================
# ⚙️ CONFIGURATION GLOBALE
# ==========================================
# Instanciation globale du générateur d'User-Agent pour éviter de le recharger à chaque requête
ua_generator = UserAgent(browsers=['chrome', 'edge', 'safari'], os=['windows', 'macos'])

# ==========================================
# 🧠 FONCTIONS DE CONFORMITÉ ET SÉCURITÉ
# ==========================================

def get_modern_headers():
    """ 
    Génère des en-têtes propres pour HTTP/2.
    Ajout du header 'From' (RFC 9110) pour montrer une identité B2B transparente.
    """
    return {
        "User-Agent": ua_generator.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5,fr-FR;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "From": "bot@outreachbrowser.com" # À remplacer par votre vrai domaine plus tard
    }

def is_allowed_by_robots(url, user_agent):
    """ Vérifie si le site nous autorise à le lire (Respect CNIL/IETF) """
    try:
        parsed_url = urllib.parse.urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        rp = robotparser.RobotFileParser()
        rp.set_url(f"{base_url}/robots.txt")
        rp.read() 
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True # En cas d'erreur de lecture, on part du principe que c'est ouvert

def is_captcha_or_blocked(html_content, status_code):
    """ Détecte si un pare-feu (ex: Cloudflare) nous bloque l'accès """
    if status_code in [401, 403]: 
        return True
    text = html_content.lower()
    anti_bot_keywords = [
        "verify you are human", "attention required! | cloudflare", 
        "unusual traffic from your computer network", "captcha"
    ]
    return any(kw in text for kw in anti_bot_keywords)

def is_honeypot_link(a_tag):
    """ Détecte les faux liens invisibles placés par les WAF pour piéger les bots """
    rel = a_tag.get('rel', [])
    if isinstance(rel, list) and 'nofollow' in [r.lower() for r in rel]:
        return True
    if isinstance(rel, str) and 'nofollow' in rel.lower():
        return True
        
    if a_tag.get('aria-hidden') == 'true':
        return True
        
    style = a_tag.get('style', '').lower()
    if 'display:none' in style or 'display: none' in style:
        return True
    if 'visibility:hidden' in style or 'visibility: hidden' in style:
        return True
        
    return False

# ==========================================
# 🛠️ FONCTIONS UTILITAIRES (Texte & Réseau)
# ==========================================

def extract_visible_text(html_content):
    """ Nettoie le HTML pour ne garder que le texte utile à l'IA et aux Regex """
    soup = BeautifulSoup(html_content, 'html.parser')
    for element in soup(["script", "style", "noscript", "meta", "nav", "footer", "header"]):
        element.extract()
    text = soup.get_text(separator=' ', strip=True)
    return re.sub(r'\s+', ' ', text)[:4000]

def fetch_with_retry(client, url, max_retries=3):
    """ Logique de relance intelligente avec gestion du Rate Limiting (429) """
    for attempt in range(max_retries):
        try:
            response = client.get(url)
            
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 2))
                time.sleep(retry_after)
                continue
                
            if response.status_code in [500, 502, 503, 504]:
                time.sleep(1.5 ** attempt)
                continue
                
            return response
            
        except httpx.RequestError:
            if attempt == max_retries - 1:
                raise
            time.sleep(1.5 ** attempt)
            
    return None

# ==========================================
# 🌐 INTELLIGENCE DE PARCOURS (Langue & Priorité)
# ==========================================

def detect_website_language(html_content, visible_text):
    """ Détecte la langue principale du site (Méthode déterministe puis NLP) """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    html_tag = soup.find('html')
    if html_tag and html_tag.get('lang'):
        lang = html_tag.get('lang')[:2].lower()
        if lang.isalpha(): 
            return lang
            
    if visible_text and len(visible_text) > 50:
        try:
            return detect(visible_text)
        except LangDetectException:
            pass
            
    return 'en'

def find_best_secondary_page(base_url, soup, language='en'):
    """ Analyse les liens de l'accueil et choisit la meilleure page (Légal > Contact > Équipe) """
    scored_links = []
    
    legal_keywords = ['legal', 'privacy', 'terms']
    if language == 'fr':
        legal_keywords = ['mention', 'legal', 'confidentialite']
    elif language == 'de':
        legal_keywords = ['impressum', 'datenschutz']
    elif language == 'es':
        legal_keywords = ['aviso', 'legal', 'privacidad']

    priority_keywords = {
        'legal': (3, legal_keywords),
        'contact': (2, ['contact', 'coordonnee', 'acces', 'location', 'reach', 'ubicacion']),
        'team': (1, ['about', 'propos', 'equipe', 'team', 'qui-sommes', 'nosotros', 'leadership'])
    }
    
    for a_tag in soup.find_all('a', href=True):
        if is_honeypot_link(a_tag): 
            continue
            
        href = a_tag['href'].lower()
        text = a_tag.get_text(strip=True).lower()
        
        if href.startswith('#') or href.startswith('javascript:'): 
            continue
            
        full_url = urllib.parse.urljoin(base_url, a_tag['href'])
        
        # On s'assure de ne pas quitter le site (ex: liens externes Facebook/LinkedIn)
        if urllib.parse.urlparse(full_url).netloc != urllib.parse.urlparse(base_url).netloc:
            continue

        best_score = 0
        for category, (score, keywords) in priority_keywords.items():
            if any(kw in href or kw in text for kw in keywords):
                if score > best_score:
                    best_score = score
                    
        if best_score > 0:
            scored_links.append((best_score, full_url))
            
    scored_links.sort(key=lambda x: x[0], reverse=True)
    return scored_links[0][1] if scored_links else None

# ==========================================
# 🚀 POINT D'ENTRÉE PRINCIPAL
# ==========================================
def inspect_website(url):
    """ Visite le site, détecte la langue, extrait le texte et les données de contact (Lazy Crawling) """
    if not url.startswith('http'):
        url = 'https://' + url

    result = {
        'http_status': None,
        'scraped_text': '',
        'contact_page_url': None,
        'language': 'en',
        'error': None,
        'is_blocked': False,
        'extracted_data': {} # <-- NOUVEAU : Contiendra nos emails, tels, adresses, dirigeants
    }

    headers = get_modern_headers()
    
    # if not is_allowed_by_robots(url, headers['User-Agent']):
    #     result['is_blocked'] = True
    #     result['error'] = "Bloqué par robots.txt"
    #     return result

    with httpx.Client(headers=headers, http2=True, verify=False, timeout=10.0, follow_redirects=True) as client:
        try:
            time.sleep(random.uniform(0.5, 1.5))
            
            # ==========================================
            # ÉTAPE 1 : VISITE DE L'ACCUEIL
            # ==========================================
            response = fetch_with_retry(client, url)
            if not response:
                raise httpx.RequestError("Max retries exceeded")
                
            result['http_status'] = response.status_code
            
            if is_captcha_or_blocked(response.text, response.status_code):
                result['is_blocked'] = True
                result['error'] = "Protégé par CAPTCHA / WAF"
                return result
                
            response.raise_for_status() 
            home_html = response.text
            visible_home_text = extract_visible_text(home_html)
            
            detected_lang = detect_website_language(home_html, visible_home_text)

            result['language'] = detected_lang
            result['scraped_text'] += visible_home_text + "\n\n"

            parsed_url = urllib.parse.urlparse(url)
            base_domain = parsed_url.netloc.replace('www.', '')

            # --- NOUVEAU : On lance l'extracteur sur l'Accueil ---
            extractor = ContactExtractor(base_domain=base_domain, language=detected_lang)
            extracted_data, is_complete = extractor.process(home_html)
            
            # ==========================================
            # ÉTAPE 2 : LE "LAZY CRAWLING" (Condition d'arrêt)
            # ==========================================
            if is_complete:
                # MAGIQUE ! On a déjà l'email, le tel et le dirigeant. On arrête les frais.
                result['extracted_data'] = extracted_data
                return result

            # ==========================================
            # ÉTAPE 3 : VISITE DE LA PAGE SECONDAIRE (S'il manque des infos)
            # ==========================================
            soup = BeautifulSoup(home_html, 'html.parser')
            best_secondary_url = find_best_secondary_page(url, soup, detected_lang)
            
            if best_secondary_url:
                result['contact_page_url'] = best_secondary_url
                time.sleep(random.uniform(0.5, 1.0)) 
                
                contact_response = fetch_with_retry(client, best_secondary_url)
                if contact_response and contact_response.status_code == 200:
                    if not is_captcha_or_blocked(contact_response.text, 200):
                        result['scraped_text'] += "--- SECONDARY PAGE ---\n" + extract_visible_text(contact_response.text)
                        
                        # --- NOUVEAU : On repasse l'extracteur sur la 2ème page ---
                        # (Il conserve les scores de la page d'accueil et s'enrichit)
                        extracted_data, is_complete = extractor.process(contact_response.text)

            # On sauvegarde les données finales consolidées
            result['extracted_data'] = extracted_data

        except httpx.RequestError as e:
            result['error'] = "Erreur réseau (Timeout ou refus)"
            if not result['http_status']:
                result['http_status'] = 0
                
    return result