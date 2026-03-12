# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/security/sanitizer.py

import copy
import re
from typing import Any

class PayloadSanitizer:
    """
    Composant de sécurité pur.
    Parcourt les payloads, headers et erreurs pour masquer les données sensibles
    avant leur journalisation ou leur stockage dans le context_snapshot.
    """

    # Liste enrichie selon les standards d'API et d'authentification
    SENSITIVE_KEY_PATTERNS = {
        'authorization', 'password', 'secret', 'token', 
        'api_key', 'cookie', 'access_token', 'client_secret',
        'stripe_key', 'cvv', 'credit_card', 'session_id',
        'refresh_token', 'webhook_secret', 'signing_secret', 'private_key'
    }

    URL_AUTH_REGEX = re.compile(r'(https?://)([^:@"/]+):([^:@"/]+)@')

    @classmethod
    def sanitize(cls, data: Any) -> Any:
        try:
            data_copy = copy.deepcopy(data)
            return cls._sanitize_recursive(data_copy)
        except Exception:
            return "<Unserializable/Unsanitizable Data>"

    @classmethod
    def _sanitize_recursive(cls, data: Any) -> Any:
        if isinstance(data, dict):
            clean_dict = {}
            for key, value in data.items():
                if cls._is_sensitive_key(str(key)):
                    clean_dict[key] = "[REDACTED]"
                else:
                    clean_dict[key] = cls._sanitize_recursive(value)
            return clean_dict
            
        elif isinstance(data, list):
            return [cls._sanitize_recursive(item) for item in data]
            
        elif isinstance(data, str):
            return cls._sanitize_string(data)
            
        return data

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        key_lower = key.lower()
        for pattern in cls.SENSITIVE_KEY_PATTERNS:
            if pattern in key_lower:
                return True
        return False

    @classmethod
    def _sanitize_string(cls, text: str) -> str:
        text = cls.URL_AUTH_REGEX.sub(r'\1[REDACTED]:[REDACTED]@', text)
        
        if text.lower().startswith("bearer ") and len(text) > 20:
            return "Bearer [REDACTED]"
        if text.lower().startswith("basic ") and len(text) > 15:
            return "Basic [REDACTED]"
            
        return text