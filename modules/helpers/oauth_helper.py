# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/helpers/oauth_helper.py

import importlib
import time
from typing import Dict, Any, Optional

import applications.reasoningframe.modules.helpers.http_helper as helpers_http
import applications.reasoningframe.modules.engine.errors as engine_errors

importlib.reload(helpers_http)
importlib.reload(engine_errors)


class OAuthHelper:
    """
    Façade OAuth minimale et purement fonctionnelle.

    RÔLE :
    - Construire des headers Authorization OAuth.
    - Vérifier l'expiration d'un token.
    - Rafraîchir un access token via un appel HTTP (délégué).
    
    NE FAIT PAS :
    - De lecture/écriture en base de données (DAL).
    - De déchiffrement de secret (délégué au CredentialService).
    - D'orchestration métier globale.
    """

    DEFAULT_EXPIRY_SKEW_SECONDS = 60

    # ==============================================================
    # 1. Validation minimale du secret OAuth
    # ==============================================================
    @classmethod
    def validate_oauth_secret(cls, secret_dict: Dict[str, Any]) -> None:
        if not isinstance(secret_dict, dict):
            raise engine_errors.N8nLifeEngineError(
                message="Le secret OAuth doit être un dictionnaire.",
                error_code="ERR_OAUTH_SECRET_INVALID"
            )

        # Validation de l'access token s'il est présent
        access_token = secret_dict.get("access_token")
        if access_token is not None and not isinstance(access_token, str):
            raise engine_errors.N8nLifeEngineError(
                message="Le champ 'access_token' doit être une string.",
                error_code="ERR_OAUTH_ACCESS_TOKEN_INVALID"
            )

        # Validation du type de token (Bearer par défaut)
        token_type = secret_dict.get("token_type", "Bearer")
        if not isinstance(token_type, str) or not token_type.strip():
            raise engine_errors.N8nLifeEngineError(
                message="Le champ 'token_type' doit être une string non vide.",
                error_code="ERR_OAUTH_TOKEN_TYPE_INVALID"
            )

        # Validation de l'expiration
        expires_at = secret_dict.get("expires_at")
        if expires_at is not None:
            try:
                float(expires_at)
            except (ValueError, TypeError):
                raise engine_errors.N8nLifeEngineError(
                    message="Le champ 'expires_at' doit être un timestamp numérique.",
                    error_code="ERR_OAUTH_EXPIRES_AT_INVALID"
                )

    # ==============================================================
    # 2. Construction d'un header OAuth standard
    # ==============================================================
    @classmethod
    def build_auth_headers(cls, secret_dict: Dict[str, Any]) -> Dict[str, str]:
        cls.validate_oauth_secret(secret_dict)

        access_token = secret_dict.get("access_token")
        token_type = secret_dict.get("token_type", "Bearer").strip()

        if not access_token:
            raise engine_errors.N8nLifeEngineError(
                message="Impossible de construire le header OAuth : access_token absent.",
                error_code="ERR_OAUTH_ACCESS_TOKEN_MISSING"
            )

        return {
            "Authorization": f"{token_type} {access_token}"
        }

    # ==============================================================
    # 3. Vérification d'expiration
    # ==============================================================
    @classmethod
    def is_token_expired(
        cls,
        secret_dict: Dict[str, Any],
        skew_seconds: int = DEFAULT_EXPIRY_SKEW_SECONDS
    ) -> bool:
        cls.validate_oauth_secret(secret_dict)

        expires_at = secret_dict.get("expires_at")
        if expires_at is None:
            # Pas d'info d'expiration = on le considère valide, mais sans garantie
            return False

        now_ts = time.time()
        # Si le timestamp d'expiration est inférieur à (maintenant + marge de sécurité), il est expiré
        return float(expires_at) <= (now_ts + skew_seconds)

    # ==============================================================
    # 4. Refresh token standardisé
    # ==============================================================
    @classmethod
    def refresh_access_token(
        cls,
        secret_dict: Dict[str, Any],
        http_helper: Optional[Any] = None,
        timeout: int = 20
    ) -> Dict[str, Any]:
        """
        Appelle le token endpoint OAuth pour obtenir un nouveau token.
        Retourne un dictionnaire mis à jour (sans effet de bord sur la DB).
        """
        cls.validate_oauth_secret(secret_dict)

        # Injection de dépendance ou fallback sur la classe statique
        http = http_helper or helpers_http.HttpHelper

        refresh_token = secret_dict.get("refresh_token")
        token_url = secret_dict.get("token_url")
        client_id = secret_dict.get("client_id")
        client_secret = secret_dict.get("client_secret")

        if not refresh_token:
            raise engine_errors.N8nLifeEngineError(
                message="Refresh impossible : 'refresh_token' absent.",
                error_code="ERR_OAUTH_REFRESH_TOKEN_MISSING"
            )

        if not token_url or not isinstance(token_url, str):
            raise engine_errors.N8nLifeEngineError(
                message="Refresh impossible : 'token_url' absent ou invalide.",
                error_code="ERR_OAUTH_TOKEN_URL_MISSING"
            )

        if not client_id or not isinstance(client_id, str):
            raise engine_errors.N8nLifeEngineError(
                message="Refresh impossible : 'client_id' absent ou invalide.",
                error_code="ERR_OAUTH_CLIENT_ID_MISSING"
            )

        if not client_secret or not isinstance(client_secret, str):
            raise engine_errors.N8nLifeEngineError(
                message="Refresh impossible : 'client_secret' absent ou invalide.",
                error_code="ERR_OAUTH_CLIENT_SECRET_MISSING"
            )

        # Préparation du payload standard OAuth2
        form_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret
        }

        # Ajout du scope optionnel s'il est présent et valide
        scope = secret_dict.get("scope")
        if isinstance(scope, str) and scope.strip():
            form_data["scope"] = scope

        try:
            # Appel réseau délégué
            response_data = http.send_request(
                method="POST",
                url=token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data_body=form_data,
                timeout=timeout
            )
        except engine_errors.NodeExecutionError as e:
            raise engine_errors.N8nLifeEngineError(
                message=f"Échec HTTP du refresh OAuth : {str(e)}",
                error_code="ERR_OAUTH_REFRESH_HTTP_FAILED",
                details=getattr(e, "details", {})
            )

        status_code = response_data.get("status_code")
        body = response_data.get("body")

        # Validation stricte de la réponse du serveur OAuth
        if not isinstance(body, dict):
            raise engine_errors.N8nLifeEngineError(
                message="Réponse OAuth invalide : body JSON dict attendu.",
                error_code="ERR_OAUTH_REFRESH_INVALID_RESPONSE",
                details={"status_code": status_code}
            )

        new_access_token = body.get("access_token")
        if not new_access_token or not isinstance(new_access_token, str):
            raise engine_errors.N8nLifeEngineError(
                message="Réponse OAuth invalide : 'access_token' absent.",
                error_code="ERR_OAUTH_REFRESH_NO_ACCESS_TOKEN",
                details={"status_code": status_code}
            )

        # Extraction des autres champs utiles
        token_type = body.get("token_type", secret_dict.get("token_type", "Bearer"))
        # Si le serveur ne renvoie pas de nouveau refresh_token, on garde l'ancien
        refresh_token_out = body.get("refresh_token", refresh_token)
        expires_in = body.get("expires_in")

        # Construction du nouveau secret
        updated_secret = dict(secret_dict)
        updated_secret["access_token"] = new_access_token
        updated_secret["refresh_token"] = refresh_token_out
        updated_secret["token_type"] = token_type

        # Calcul du nouveau timestamp d'expiration
        if expires_in is not None:
            try:
                updated_secret["expires_at"] = time.time() + float(expires_in)
            except (ValueError, TypeError):
                raise engine_errors.N8nLifeEngineError(
                    message="Réponse OAuth invalide : 'expires_in' non numérique.",
                    error_code="ERR_OAUTH_REFRESH_INVALID_EXPIRES_IN"
                )

        return updated_secret

    # ==============================================================
    # 5. Helper haut niveau : garantir un header frais
    # ==============================================================
    @classmethod
    def get_fresh_auth_headers(
        cls,
        secret_dict: Dict[str, Any],
        http_helper: Optional[Any] = None,
        auto_refresh: bool = True
    ) -> Dict[str, Any]:
        """
        Fournit les headers d'authentification, en rafraîchissant le token si nécessaire.
        
        Retourne :
        {
            "headers": {"Authorization": "Bearer ..."},
            "updated_secret": {...} ou None si pas de rafraîchissement
        }
        """
        cls.validate_oauth_secret(secret_dict)

        working_secret = dict(secret_dict)
        updated_secret = None

        if auto_refresh and cls.is_token_expired(working_secret):
            working_secret = cls.refresh_access_token(
                secret_dict=working_secret,
                http_helper=http_helper
            )
            updated_secret = working_secret

        # Construction finale avec le secret (frais ou existant)
        headers = cls.build_auth_headers(working_secret)

        return {
            "headers": headers,
            "updated_secret": updated_secret
        }