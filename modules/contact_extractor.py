import re
import json
import urllib.parse
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

# ==========================================
# 1. MODÉLISATION DES DONNÉES
# ==========================================
@dataclass
class CandidateValue:
    value: str
    source: str
    score: int

@dataclass
class PersonCandidate:
    full_name: str
    role: Optional[str]
    source: str
    score: int

# ==========================================
# 2. UTILITAIRES DE NETTOYAGE ET DÉSOBFUSCATION
# ==========================================
def is_probable_person_name(text: str) -> bool:
    """ Vérifie si la chaîne ressemble à un vrai nom (2 à 5 mots, pas d'URL) """
    text = re.sub(r'\s+', ' ', text or '').strip()
    if not (5 <= len(text) <= 80): return False
    if "@" in text or "http" in text: return False
    words = text.split()
    if not (2 <= len(words) <= 5): return False
    return all(re.match(r"^[A-Za-zÀ-ÿ'\-\.]+$", w) for w in words)

def clean_phone(phone: str) -> Optional[str]:
    """ Ne garde que les chiffres et le +, renvoie None si invalide """
    raw = re.sub(r'\s+', ' ', phone or '').strip()
    digits = re.sub(r'[^\d+]', '', raw)
    return raw if len(digits) >= 8 else None

def decrypt_cloudflare_xor_payload(cf_hex_string: str) -> Optional[str]:
    """ Rétro-ingénierie mathématique de l'obfuscation Cloudflare """
    try:
        xor_key = int(cf_hex_string[0:2], 16)
        decrypted_chars = []
        for i in range(2, len(cf_hex_string), 2):
            hex_pair = cf_hex_string[i:i+2]
            encrypted_char_code = int(hex_pair, 16)
            decrypted_chars.append(chr(encrypted_char_code ^ xor_key))
        raw_email_string = ''.join(decrypted_chars)
        quoted_string = urllib.parse.quote(raw_email_string, encoding='latin-1')
        final_decoded = urllib.parse.unquote(quoted_string)
        # On valide que c'est bien un email à la fin
        match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', final_decoded)
        return match.group(0) if match else None
    except Exception:
        return None

def normalize_heuristic_email_obfuscation(raw_text: str) -> List[str]:
    """ Répare les emails altérés typographiquement (ex: contact [at] site.com) """
    normalized = re.sub(r'(?i)\s*(\[at\]|\(at\)|\[arobase\]|@| at )\s*', '@', raw_text)
    normalized = re.sub(r'(?i)\s*(\[dot\]|\(dot\)|\[point\]| dot )\s*', '.', normalized)
    return re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', normalized)

# ==========================================
# 3. MOTEUR D'EXTRACTION EN CASCADE
# ==========================================
class ContactExtractor:
    def __init__(self, base_domain: str, language: str = 'en'):
        self.language = language
        self.base_domain = base_domain.replace('www.', '').lower()
        
        # Stockage sous forme de dictionnaire pour dédupliquer par clé unique
        self.emails_candidates = {}
        self.phones_candidates = {}
        self.addresses_candidates = {}
        self.executives_candidates = {}

    def add_candidate(self, bucket: dict, raw_value: str, value_obj: Any):
        """ Ajoute le candidat. S'il existe déjà avec un score plus faible, on l'écrase. """
        if not raw_value: return
        key = raw_value.lower()
        
        if key in bucket:
            if value_obj.score > bucket[key].score:
                bucket[key] = value_obj
        else:
            bucket[key] = value_obj

    def extract_json_ld(self, soup: BeautifulSoup):
        """ Score: 100 - Les données structurées SEO """
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.get_text(strip=True))
                data_list = data if isinstance(data, list) else [data]
                for item in data_list:
                    nodes = item.get('@graph', [item])
                    for node in nodes:
                        if node.get('@type') in ['Organization', 'LocalBusiness']:
                            # Email & Téléphone
                            if node.get('email'):
                                email = node.get('email').replace('mailto:', '').strip()
                                self.add_candidate(self.emails_candidates, email, CandidateValue(email, "jsonld", 100))
                            if node.get('telephone'):
                                phone = clean_phone(str(node.get('telephone')))
                                if phone: self.add_candidate(self.phones_candidates, phone, CandidateValue(phone, "jsonld", 100))
                            
                            # Adresse Structurée
                            addr = node.get('address')
                            if isinstance(addr, dict):
                                parts = [addr.get('streetAddress'), addr.get('postalCode'), addr.get('addressLocality')]
                                full_addr = ", ".join([str(p) for p in parts if p])
                                if full_addr: self.add_candidate(self.addresses_candidates, full_addr, CandidateValue(full_addr, "jsonld", 100))
                            elif isinstance(addr, str):
                                self.add_candidate(self.addresses_candidates, addr, CandidateValue(addr, "jsonld", 100))
                                
                        # Dirigeants / Personnes
                        elif node.get('@type') == 'Person' and node.get('jobTitle') and node.get('name'):
                            title = str(node['jobTitle']).lower()
                            name = str(node['name']).strip()
                            if is_probable_person_name(name) and any(kw in title for kw in ['ceo', 'founder', 'directeur', 'gérant', 'president', 'partner']):
                                self.add_candidate(self.executives_candidates, name, PersonCandidate(name, title.title(), "jsonld", 100))
            except Exception:
                continue

    def extract_legal_executives(self, visible_text: str):
        """ Score: 95 - Recherche par expressions régulières juridiques européennes """
        patterns = {
            'fr': r'(?i)(?:Directeur de(?: la)? publication|Responsable de(?: la)? r[é|e]daction|G[é|e]rant|Président)\s*[:\s\-]+([A-ZÀ-Ÿ][a-zA-ZÀ-ÿ\s\.\-]+)',
            'de': r'(?i)(?:Geschäftsführer|Vertreten durch|Inhaber)(?:in)?\s*[:\n\-]?\s*([A-ZÄÖÜ][a-zA-Zäöüß\s\.\-]+)',
            'es': r'(?i)(?:Representante legal|Administrador(?:a)? [úu]nico|Director(?:a)?)\s*[:\s\-]?\s*([A-ZÁÉÍÓÚÑ][a-zA-Záéíóúñ\s\.\-]+)',
            'en': r'(?i)(?:Managing Director|Director|Company Secretary|CEO|Founder)\s*[:\s\-]?\s*([A-Z][a-zA-Z\s\.\-]+)'
        }
        regex = patterns.get(self.language, patterns['en'])
        for match in re.findall(regex, visible_text):
            name = match.strip()
            if is_probable_person_name(name):
                self.add_candidate(self.executives_candidates, name, PersonCandidate(name, "Legal Representative", "legal_regex", 95))

    def extract_html_tags(self, soup: BeautifulSoup):
        """ Score: 90 - Balises déterministes (mailto, tel, address) """
        for a in soup.find_all('a', href=re.compile(r'(?i)^mailto:')):
            email = a['href'].replace('mailto:', '').split('?')[0].strip()
            if '@' in email:
                self.add_candidate(self.emails_candidates, email, CandidateValue(email, "mailto", 90))
                
        for a in soup.find_all('a', href=re.compile(r'(?i)^tel:')):
            phone = clean_phone(a['href'].replace('tel:', ''))
            if phone:
                self.add_candidate(self.phones_candidates, phone, CandidateValue(phone, "tel", 90))

        for addr_tag in soup.find_all('address'):
            text = addr_tag.get_text(separator=', ', strip=True)
            if len(text) > 10:
                self.add_candidate(self.addresses_candidates, text, CandidateValue(text, "address_tag", 90))

    def extract_microformats(self, soup: BeautifulSoup):
        """ Score: 80 - Frameworks CSS (Bootstrap, Webflow, BEM) """
        for card in soup.select('.h-card, .vcard, .team-member, [class*="team-card"], [class*="member"]'):
            name_node = card.select_one('.p-name, .fn, [class*="name"], h3, h4')
            role_node = card.select_one('.p-job-title, [class*="role"], [class*="job"]')
            
            if name_node:
                name = name_node.get_text(strip=True)
                if is_probable_person_name(name):
                    role = role_node.get_text(strip=True) if role_node else None
                    self.add_candidate(self.executives_candidates, name, PersonCandidate(name, role, "microformats", 80))

    def extract_cloudflare_emails(self, soup: BeautifulSoup):
        """ Score: 80 - Déchiffrement mathématique des emails protégés """
        for node in soup.find_all(attrs={'data-cfemail': True}):
            clear_email = decrypt_cloudflare_xor_payload(node['data-cfemail'])
            if clear_email:
                self.add_candidate(self.emails_candidates, clear_email, CandidateValue(clear_email, "cloudflare_xor", 80))

    def extract_regex_fallback(self, visible_text: str):
        """ Score: 20 & 60 - Recherche à l'aveugle dans le texte """
        # Emails altérés typographiquement
        for email in normalize_heuristic_email_obfuscation(visible_text):
            self.add_candidate(self.emails_candidates, email, CandidateValue(email, "heuristic_email", 60))

        # Emails standards en brut
        for match in re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', visible_text):
            self.add_candidate(self.emails_candidates, match, CandidateValue(match, "regex_fallback", 20))

        # Téléphones en brut
        phone_pattern = r'(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\(?\d{1,4}\)?[\s.-]?)?(?:\d{2,4}[\s.-]?){2,4}\d{2,4}'
        for match in re.findall(phone_pattern, visible_text):
            phone = clean_phone(match)
            if phone:
                self.add_candidate(self.phones_candidates, match.strip(), CandidateValue(match.strip(), "regex_fallback", 20))

    # ==========================================
    # LANCEMENT DU PIPELINE EN CASCADE
    # ==========================================
    def process(self, html_content: str):
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Destruction des Honeypots CSS (Anti-Trap)
        for hidden in soup.find_all(style=re.compile(r'display:\s*none|visibility:\s*hidden', re.I)):
            hidden.decompose()
            
        visible_text = soup.get_text(separator=' ', strip=True)

        # 2. Exécution de la cascade de la source la plus sûre à la moins sûre
        self.extract_json_ld(soup)
        self.extract_html_tags(soup)
        self.extract_microformats(soup)
        self.extract_cloudflare_emails(soup)
        self.extract_legal_executives(visible_text)
        self.extract_regex_fallback(visible_text)

        # 3. Formatage et Tri final par score
        results = {
            'company_domain': self.base_domain,
            'emails': [asdict(c) for c in sorted(self.emails_candidates.values(), key=lambda x: x.score, reverse=True)],
            'phones': [asdict(c) for c in sorted(self.phones_candidates.values(), key=lambda x: x.score, reverse=True)],
            'addresses': [asdict(c) for c in sorted(self.addresses_candidates.values(), key=lambda x: x.score, reverse=True)],
            'executives': [asdict(c) for c in sorted(self.executives_candidates.values(), key=lambda x: x.score, reverse=True)]
        }

        # 4. Identification du "Best Email" avec validation de domaine
        best_email = None
        if results['emails']:
            # Privilégie un email contenant le domaine (ex: contact@societe.com au lieu de agenceweb@gmail.com)
            domain_emails = [e for e in results['emails'] if self.base_domain in e['value']]
            best_email = domain_emails[0] if domain_emails else results['emails'][0]
        
        results['best_email'] = best_email

        # 5. Détermination du Lazy Crawling (Faut-il visiter une autre page ?)
        # True si nous avons au moins un email pertinent, un téléphone, et un dirigeant.
        is_complete = bool(results['best_email'] and results['phones'] and results['executives'])

        return results, is_complete