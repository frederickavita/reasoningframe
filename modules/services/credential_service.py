# -*- coding: utf-8 -*-
# applications/n8n_life/modules/services/credential_service.py

import importlib
from typing import Dict, Any, Optional

import applications.reasoningframe.modules.security.vault as sec_vault
import applications.reasoningframe.modules.engine.errors as engine_errors

importlib.reload(sec_vault)
importlib.reload(engine_errors)

class CredentialService:
    """
    Gestionnaire métier des credentials.
    Fait le pont entre la DAL (db.user_credential) et le Vault (Cryptographie).
    Strictement cloisonné par utilisateur.
    """

    def __init__(self, db: Any, user_id: int, vault: Optional[Any] = None):
        """
        :param db: L'objet DAL global de web2py (db).
        :param user_id: L'identifiant du propriétaire des secrets (Isolation B2B).
        :param vault: Injection de dépendance pour la crypto (utilise le vrai Vault par défaut).
        """
        self.db = db
        self.user_id = user_id
        self.vault = vault or sec_vault.CredentialVault()

        # Lecture dynamique des constantes sur la classe/instance Vault 
        # (Single Source of Truth, supporte l'injection d'un MockVault)
        self.current_algo = getattr(self.vault.__class__, 'CURRENT_ALGO', getattr(self.vault, 'CURRENT_ALGO', 'AES-256-CBC-HMAC-SHA256'))
        self.current_version = getattr(self.vault.__class__, 'CURRENT_CRYPTO_VERSION', getattr(self.vault, 'CURRENT_CRYPTO_VERSION', 1))

    # =========================================================================
    # MÉTHODES POUR LE MOTEUR D'EXÉCUTION (Lecture Seule)
    # =========================================================================

    def get_decrypted_secret(self, credential_key: str) -> Dict[str, Any]:
        """
        [CONTRAT DU MOTEUR] 
        Récupère le blob en base et le déchiffre à la volée (JIT).
        Ici, 'credential_key' map strictement sur 'service_name' dans la base.
        """
        if not credential_key:
            return {}

        row = self.db(
            (self.db.user_credential.user_id == self.user_id) & 
            (self.db.user_credential.service_name == credential_key)
        ).select().first()

        if not row:
            raise engine_errors.N8nLifeEngineError(
                message=f"Le credential '{credential_key}' est introuvable ou accès refusé.",
                error_code="ERR_CREDENTIAL_NOT_FOUND",
                details={"service_name": credential_key, "user_id": self.user_id}
            )

        if not row.encrypted_data:
            raise engine_errors.N8nLifeEngineError(
                message=f"Le credential '{credential_key}' est corrompu (données absentes).",
                error_code="ERR_CREDENTIAL_CORRUPTED",
                details={"service_name": credential_key}
            )

        try:
            return self.vault.decrypt(row.encrypted_data)
        except engine_errors.N8nLifeEngineError as e:
            raise engine_errors.N8nLifeEngineError(
                message=f"Échec du déchiffrement pour '{credential_key}'. La clé maître a-t-elle changé ?",
                error_code="ERR_CREDENTIAL_DECRYPTION_FAILED",
                details={"original_error": str(e), "service_name": credential_key}
            )

    # =========================================================================
    # MÉTHODES POUR L'UI / L'API WEB2PY (Écriture)
    # =========================================================================

    def create_credential(self, service_name: str, secret_data: Dict[str, Any]) -> int:
        """
        Chiffre le dictionnaire et crée une nouvelle entrée en base.
        """
        if self._exists(service_name):
            raise engine_errors.N8nLifeEngineError(
                message=f"Un credential nommé '{service_name}' existe déjà pour cet utilisateur.",
                error_code="ERR_CREDENTIAL_ALREADY_EXISTS"
            )

        encrypted_blob = self.vault.encrypt(secret_data)

        record_id = self.db.user_credential.insert(
            user_id=self.user_id,
            service_name=service_name,
            encrypted_data=encrypted_blob,
            crypto_algo=self.current_algo,
            crypto_version=self.current_version,
            is_valid=False,  # La confiance doit être prouvée par un premier run
            last_checked_on=None
        )
        return record_id

    def update_credential(self, service_name: str, secret_data: Dict[str, Any]) -> bool:
        """
        Met à jour un credential existant et révoque immédiatement son statut de validité.
        """
        if not self._exists(service_name):
            raise engine_errors.N8nLifeEngineError(
                message=f"Le credential '{service_name}' n'existe pas.",
                error_code="ERR_CREDENTIAL_NOT_FOUND"
            )

        encrypted_blob = self.vault.encrypt(secret_data)

        updated_count = self.db(
            (self.db.user_credential.user_id == self.user_id) & 
            (self.db.user_credential.service_name == service_name)
        ).update(
            encrypted_data=encrypted_blob,
            crypto_algo=self.current_algo,
            crypto_version=self.current_version,
            is_valid=False,  # Révocation de confiance après modification
            last_checked_on=None
        )

        return updated_count > 0

    def check_credential_exists(self, service_name: str) -> bool:
        """Exposé pour la validation de graphe ou les interfaces."""
        return self._exists(service_name)

    def _exists(self, service_name: str) -> bool:
        """Vérifie l'existence physique (ignore l'état de validation)."""
        count = self.db(
            (self.db.user_credential.user_id == self.user_id) & 
            (self.db.user_credential.service_name == service_name)
        ).count()
        return count > 0