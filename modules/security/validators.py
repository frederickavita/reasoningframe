# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/security/validators.py

import hmac
import hashlib
import time
from typing import Dict, Optional, List

import importlib
import applications.reasoningframe.modules.engine.errors as engine_errors
importlib.reload(engine_errors)

class WebhookValidator:
    """
    Composant de validation cryptographique pur.
    Vérifie l'authenticité et l'intégrité des appels entrants (Webhooks).
    """

    TIMESTAMP_TOLERANCE_SECONDS = 300 

    @classmethod
    def validate(cls, 
                 raw_body: bytes, 
                 headers: Dict[str, str], 
                 shared_secret: Optional[str], 
                 strategy: str, 
                 signature_header_key: Optional[str] = None):
        
        # 1. Stratégie Ouverte (À utiliser avec extrême prudence côté applicatif)
        if strategy == "none":
            return
            
        if not shared_secret:
            raise engine_errors.WebhookValidationError(
                "Un secret partagé est requis pour cette stratégie.",
                details={"strategy": strategy}
            )

        # Normalisation des headers en minuscules une seule fois
        headers_lower = {k.lower(): v for k, v in headers.items()}

        # 2. Stratégie Custom HMAC
        if strategy == "custom_hmac":
            cls._validate_custom_hmac(raw_body, headers_lower, shared_secret, signature_header_key)
            
        # 3. Stratégie Stripe
        elif strategy == "stripe_hmac":
            cls._validate_stripe(raw_body, headers_lower, shared_secret)
            
        else:
            raise engine_errors.WebhookValidationError(
                f"Stratégie de validation non supportée : '{strategy}'",
                details={"strategy": strategy}
            )

    @classmethod
    def _validate_custom_hmac(cls, raw_body: bytes, headers_lower: Dict[str, str], secret: str, header_key: str):
        if not header_key:
            raise engine_errors.WebhookValidationError("Le nom du header de signature est manquant pour custom_hmac.")
            
        provided_signature = headers_lower.get(header_key.lower())
        if not provided_signature:
            raise engine_errors.WebhookValidationError(f"Le header '{header_key}' est absent de la requête.")

        # Nettoyage des préfixes courants (ex: GitHub utilise "sha256=...", certains utilisent "mac=...")
        provided_signature = provided_signature.replace("sha256=", "").replace("mac=", "").strip()

        mac = hmac.new(secret.encode('utf-8'), msg=raw_body, digestmod=hashlib.sha256)
        expected_signature = mac.hexdigest()

        if not hmac.compare_digest(expected_signature, provided_signature):
            raise engine_errors.WebhookValidationError("La signature HMAC personnalisée est invalide.")

    @classmethod
    def _validate_stripe(cls, raw_body: bytes, headers_lower: Dict[str, str], secret: str):
        stripe_header = headers_lower.get("stripe-signature")
        if not stripe_header:
            raise engine_errors.WebhookValidationError("Le header 'Stripe-Signature' est absent.")

        # Parsing robuste : extraction du timestamp (t) et de TOUTES les signatures (v1)
        timestamp_str = None
        signatures_v1: List[str] = []
        
        for part in stripe_header.split(","):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if key == "t":
                timestamp_str = value
            elif key == "v1":
                signatures_v1.append(value)

        if not timestamp_str or not signatures_v1:
            raise engine_errors.WebhookValidationError("Timestamp (t) ou signatures (v1) manquants.")

        try:
            timestamp = int(timestamp_str)
        except ValueError:
            raise engine_errors.WebhookValidationError("Le timestamp Stripe n'est pas un entier.")

        if abs(time.time() - timestamp) > cls.TIMESTAMP_TOLERANCE_SECONDS:
            raise engine_errors.WebhookValidationError("Timestamp Stripe expiré (Suspicion de Replay Attack).")

        signed_payload = f"{timestamp_str}.".encode('utf-8') + raw_body
        mac = hmac.new(secret.encode('utf-8'), msg=signed_payload, digestmod=hashlib.sha256)
        expected_signature = mac.hexdigest()

        # Validation : Il suffit qu'UNE seule des signatures v1 corresponde (Gestion du Secret Rollover Stripe)
        for provided_sig in signatures_v1:
            if hmac.compare_digest(expected_signature, provided_sig):
                return # Succès

        # Si on sort de la boucle sans succès :
        raise engine_errors.WebhookValidationError("Aucune des signatures Stripe fournies n'est valide.")