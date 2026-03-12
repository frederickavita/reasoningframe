# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/helpers/http_helper.py

import requests
from typing import Any, Dict, Optional
import importlib

# Imports web2py avec reload
import applications.reasoningframe.modules.engine.errors as engine_errors
importlib.reload(engine_errors)

import applications.reasoningframe.modules.security.sanitizer as security_sanitizer
importlib.reload(security_sanitizer)

class HttpHelper:
    """
    Façade réseau centralisée (Plomberie HTTP sortante).
    Agnostique du métier : exécute fidèlement, normalise la réponse et sécurise les logs.
    """
    
    # Règle architecturale : 20 secondes max pour ne pas bloquer les workers web2py
    DEFAULT_TIMEOUT = 20

    @classmethod
    def send_request(cls, 
                     method: str, 
                     url: str, 
                     headers: Optional[Dict[str, str]] = None, 
                     query_params: Optional[Dict[str, Any]] = None,
                     json_body: Optional[Any] = None,
                     data_body: Optional[Any] = None,
                     timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
        
        method = method.upper()
        headers = headers or {}

        # 1. Vérification basique de l'URL
        if not url.startswith(('http://', 'https://')):
            raise engine_errors.NodeExecutionError(
                node_id="HTTP_HELPER", 
                message=f"URL invalide ou protocole manquant : {url}"
            )

        # Résolution sécurisée du body pour la preview (évite le bug des objets falsy)
        body_for_preview = json_body if json_body is not None else data_body

        # 2. Préparation d'une Preview Sanitizée complète
        request_preview = {
            "method": method,
            "url": url,
            "headers": security_sanitizer.PayloadSanitizer.sanitize(headers),
            "query": security_sanitizer.PayloadSanitizer.sanitize(query_params),
            "body": security_sanitizer.PayloadSanitizer.sanitize(body_for_preview)
        }

        try:
            # 3. Exécution de la requête via 'requests'
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=query_params,
                json=json_body,  
                data=data_body,  
                timeout=timeout
            )

            # 4. Normalisation stricte et sécurisée de la réponse
            return {
                "status_code": response.status_code,
                # On sanitize les headers de retour (peuvent contenir des Set-Cookie ou des Tokens)
                "headers": security_sanitizer.PayloadSanitizer.sanitize(dict(response.headers)),
                "body": cls._parse_response_body(response),
                "request_preview": request_preview  # Preview attachée au succès pour les snapshots
            }

        except requests.exceptions.Timeout:
            raise engine_errors.NodeExecutionError(
                node_id="HTTP_HELPER",
                message=f"Timeout réseau après {timeout}s",
                details={"request_preview": request_preview}
            )
        except requests.exceptions.RequestException as e:
            raise engine_errors.NodeExecutionError(
                node_id="HTTP_HELPER",
                message=f"Échec de la connexion réseau : {str(e)}",
                details={"request_preview": request_preview}
            )

    @classmethod
    def _parse_response_body(cls, response: requests.Response) -> Any:
        """Tente de parser en JSON, fallback sur texte brut."""
        if not response.content:
            return None
        
        content_type = response.headers.get('Content-Type', '').lower()
        
        if 'application/json' in content_type:
            try:
                return response.json()
            except ValueError:
                return response.text
        
        return response.text