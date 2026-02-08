# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------
# ADPATROL ENGINE - cron_monitor.py (Version Émeraude)
# Statut: Production Grade
# Fixes: Lock Atomique (EEXIST), Google OneOf, Path handling, -N context
# -------------------------------------------------------------------------

import os
import sys
import datetime
import logging
import time
import errno
from decimal import Decimal, InvalidOperation
from typing import List, Tuple, Optional

# --- Google Ads SDK (EAFP) ---
try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
    from google.api_core import protobuf_helpers
except ImportError as e:
    raise RuntimeError("Dépendance manquante : installez 'google-ads'") from e

# =============================================================================
# 1. Configuration & Constantes
# =============================================================================
WARNING_THRESHOLD_PERCENT = 90
MICROS_PER_UNIT = Decimal("1000000")
LOCK_TIMEOUT_SECONDS = 3600  # 1h max

def _get_logger() -> logging.Logger:
    logger = logging.getLogger("adpatrol")
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

logger = _get_logger()

# =============================================================================
# 2. Helpers Robustes (Locking & Paths)
# =============================================================================

def get_lock_file_path() -> str:
    """Calcule le chemin du lock de manière safe (Web2py Runtime vs Shell)."""
    try:
        # Contexte Web2py standard
        base_folder = request.folder
    except NameError:
        # Fallback: chemin relatif au script actuel
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Si on est déjà dans 'private', on remonte d'un cran pour avoir la racine app
        if os.path.basename(current_dir) == 'private':
            base_folder = os.path.dirname(current_dir)
        else:
            base_folder = current_dir
    
    private_folder = os.path.join(base_folder, 'private')
    if not os.path.exists(private_folder):
        os.makedirs(private_folder, exist_ok=True)
        
    return os.path.join(private_folder, 'adpatrol_cron.lock')

def acquire_lock_atomic() -> bool:
    """
    Tente d'acquérir un lock exclusif (O_EXCL).
    Gère le nettoyage des locks périmés (stale) et les erreurs système réelles.
    """
    lock_path = get_lock_file_path()
    
    # 1. Nettoyage préventif si périmé
    if os.path.exists(lock_path):
        try:
            mtime = os.path.getmtime(lock_path)
            age = time.time() - mtime
            if age > LOCK_TIMEOUT_SECONDS:
                logger.warning(f"⚠️ Lock périmé ({int(age)}s). Suppression forcée.")
                os.remove(lock_path)
        except OSError:
            pass # Fichier disparu entre temps (race condition bénigne)

    # 2. Création Atomique
    try:
        # O_CREAT | O_EXCL : Échoue si le fichier existe (Atomicité OS)
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, 'w') as f:
            f.write(str(os.getpid()))
        return True
    
    except OSError as e:
        if e.errno == errno.EEXIST:
            # Le fichier existe déjà -> Un autre process tourne
            logger.warning("🔒 Lock actif. Une autre instance tourne. Abandon.")
            return False
        else:
            # Vraie erreur système (Disque plein, permissions...)
            logger.critical(f"ERREUR SYSTÈME LOCK: {e}")
            raise e

def release_lock():
    lock_path = get_lock_file_path()
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except OSError as e:
        logger.error(f"Erreur suppression lock: {e}")

# =============================================================================
# 3. Helpers Google Ads (Error Handling & API)
# =============================================================================

def format_google_ads_exception(ex: GoogleAdsException) -> str:
    parts = []
    rid = getattr(ex, "request_id", "")
    if rid: parts.append(f"RequestId: {rid}")
    
    failure = getattr(ex, "failure", None)
    if failure and getattr(failure, "errors", None):
        for err in failure.errors:
            parts.append(f"{err.message}")
    else:
        parts.append(str(ex))
    return " | ".join(parts)

def is_fatal_google_error(ex: GoogleAdsException) -> bool:
    """Détermine si l'erreur justifie un arrêt définitif (ERROR status) via OneOf."""
    failure = getattr(ex, "failure", None)
    if not (failure and getattr(failure, "errors", None)):
        return False

    # Codes qui nécessitent une intervention humaine (STOP)
    fatal_types = {"authentication_error", "authorization_error", "request_error"}
    # Codes transitoires (RETRY)
    transient_types = {"quota_error", "internal_error", "temporary_error"}

    for err in failure.errors:
        # Protobuf way: quel champ est rempli dans le oneof "error_code" ?
        which = err.error_code.WhichOneof("error_code")
        
        if which in fatal_types:
            return True
        if which in transient_types:
            return False

    # Par défaut, si on ne connait pas l'erreur, on assume transitoire (Retry)
    return False

# =============================================================================
# 4. Logique Métier (Pure Functions)
# =============================================================================

def normalize_customer_id(raw: str) -> str:
    cid = raw.replace("-", "").strip()
    if not cid.isdigit():
        raise ValueError(f"ID Client invalide: {raw}")
    return cid

def fetch_month_spend_eur(ga_service, customer_id: str) -> Decimal:
    query = """
        SELECT metrics.cost_micros 
        FROM customer 
        WHERE segments.date DURING THIS_MONTH
    """
    total_micros = 0
    response = ga_service.search_stream(customer_id=customer_id, query=query)
    for batch in response:
        for row in batch.results:
            # V17+ API Access pattern
            total_micros += row.metrics.cost_micros
            
    return Decimal(total_micros) / MICROS_PER_UNIT

def compute_risk_status(current_spend: Decimal, budget: Decimal) -> Tuple[int, str]:
    if budget <= Decimal("0"): return (0, "OK")
    
    percent = int((current_spend / budget) * 100)
    status = "OK"
    if percent >= WARNING_THRESHOLD_PERCENT:
        status = "WARNING"
    if current_spend >= budget:
        status = "CRITICAL"
        
    return percent, status

def pause_campaigns(ga_service, campaign_service, gads_client, customer_id: str) -> int:
    """Trouve ET Pause les campagnes actives. Injection propre des services."""
    # 1. Lister (via ga_service)
    query = "SELECT campaign.id FROM campaign WHERE campaign.status = 'ENABLED'"
    ids = []
    # On itère proprement pour consommer le stream
    stream = ga_service.search_stream(customer_id=customer_id, query=query)
    for batch in stream:
        for row in batch.results:
            ids.append(int(row.campaign.id))
            
    if not ids: return 0

    # 2. Pauser (via campaign_service)
    operations = []
    for camp_id in ids:
        op = gads_client.get_type("CampaignOperation")
        campaign = op.update
        campaign.resource_name = campaign_service.campaign_path(customer_id, camp_id)
        campaign.status = gads_client.enums.CampaignStatusEnum.PAUSED
        # Masque obligatoire
        op.update_mask.CopyFrom(protobuf_helpers.field_mask(None, campaign._pb))
        operations.append(op)
    
    campaign_service.mutate_campaigns(customer_id=customer_id, operations=operations)
    return len(operations)

# =============================================================================
# 5. Orchestration (DB & Process)
# =============================================================================

def log_event(client_id, event_type, message, spend, budget):
    db.logs.insert(
        client_id=client_id,
        event_type=event_type,
        message=message,
        snapshot_spend=spend,
        snapshot_budget=budget
    )

def process_one_client(client, ga_service, campaign_service, gads_client, now):
    
    previous_status = client.status
    
    # 1. Conversion
    try:
        budget = Decimal(str(client.monthly_budget))
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"Budget invalide DB: {client.monthly_budget}") from e

    customer_id = normalize_customer_id(client.google_customer_id)
    
    # 2. Appel Réseau
    current_spend = fetch_month_spend_eur(ga_service, customer_id)
    percent, new_status = compute_risk_status(current_spend, budget)
    
    # 3. Kill Switch Logic
    actions_taken = 0
    if new_status == "CRITICAL" and client.kill_switch_active:
        actions_taken = pause_campaigns(ga_service, campaign_service, gads_client, customer_id)
        if actions_taken > 0:
            logger.warning(f"KILL SWITCH: client={client.id} paused={actions_taken}")

    # 4. Mise à jour DB
    client.update_record(
        current_spend=current_spend,
        spend_percent=percent,
        status=new_status,
        last_check=now
    )
    
    # 5. Logging Intelligent
    if new_status == "CRITICAL":
        if actions_taken > 0:
            log_event(client.id, "CRITICAL", 
                      f"KILL SWITCH EXÉCUTÉ. Dépense({current_spend}€) >= Budget({budget}€). {actions_taken} campagnes pausées.", 
                      current_spend, budget)
        elif previous_status != "CRITICAL":
            log_event(client.id, "CRITICAL", 
                      f"ALERTE CRITIQUE. Dépense({current_spend}€) >= Budget({budget}€).", 
                      current_spend, budget)
            
    elif new_status == "WARNING" and previous_status != "WARNING":
        log_event(client.id, "WARNING", 
                  f"Seuil {WARNING_THRESHOLD_PERCENT}% atteint. Dépense: {current_spend}€ ({percent}%).", 
                  current_spend, budget)

def run_scan():
    # 1. Lock Atomique
    if not acquire_lock_atomic():
        return

    try:
        # Gestion Timezone
        # Si on est en CLI web2py via -R, request.now est dispo et timezone-aware selon config
        try: db_now = request.now
        except NameError: db_now = datetime.datetime.utcnow()
            
        logger.info(f"DÉMARRAGE SCAN: {db_now}")
        
        # Chargement Config
        settings = db(db.settings.id > 0).select().first()
        if not settings or not settings.developer_token:
            logger.error("Configuration Agence manquante.")
            return

        # Init Google Client
        try:
            gads_client = GoogleAdsClient.load_from_dict({
                "developer_token": settings.developer_token,
                "client_id": settings.client_id,
                "client_secret": settings.client_secret,
                "refresh_token": settings.refresh_token,
                "use_proto_plus": True
            })
            ga_service = gads_client.get_service("GoogleAdsService")
            campaign_service = gads_client.get_service("CampaignService")
        except Exception as e:
            logger.critical(f"Echec Init Google Client: {e}")
            return

        monitored = db(db.clients.monthly_budget > 0).select()
        
        for client in monitored:
            if client.monthly_budget <= Decimal("0"): continue
            
            try:
                process_one_client(client, ga_service, campaign_service, gads_client, db_now)
                db.commit() 
                
            except GoogleAdsException as ex:
                db.rollback()
                error_details = format_google_ads_exception(ex)
                logger.error(f"GOOGLE ERROR client={client.id}: {error_details}")
                
                # Classification Fatal vs Transient (via OneOf)
                if is_fatal_google_error(ex):
                    client.update_record(status='ERROR', last_check=db_now)
                    log_event(client.id, "ERROR", f"Erreur Fatale: {error_details}", Decimal("0"), Decimal("0"))
                    db.commit()
                else:
                    # Transient: On loggue l'erreur mais on ne bloque pas le client (Retry next cron)
                    log_event(client.id, "ERROR", f"Erreur API (Retry): {error_details}", Decimal("0"), Decimal("0"))
                    db.commit()
                
            except Exception as ex:
                db.rollback()
                logger.error(f"SYSTEM ERROR client={client.id}: {ex}")
                try:
                    client.update_record(status='ERROR', last_check=db_now)
                    log_event(client.id, "ERROR", f"Bug Interne: {str(ex)}", Decimal("0"), Decimal("0"))
                    db.commit()
                except: pass

    finally:
        release_lock()
        logger.info("FIN SCAN")

if __name__ == '__main__':
    run_scan()