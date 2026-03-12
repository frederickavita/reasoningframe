# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/security/vault.py

import os
import json
import base64
from typing import Dict, Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes
from cryptography.hazmat.primitives.hmac import HMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import importlib
import applications.reasoningframe.modules.engine.errors as engine_errors
importlib.reload(engine_errors)

class CredentialVault:
    """
    Moteur cryptographique pur.
    Sans état métier (ne connaît ni DB, ni Node), mais maintient l'état crypto en RAM.
    
    CONTRAT OFFICIEL DU BLOB :
    Format : <version>$<base64_iv>$<base64_ciphertext>$<base64_mac>
    Exemple : v1$A1b2...$x9Y...$z8W...
    """

    CURRENT_CRYPTO_VERSION = 1

    def __init__(self):
        # Récupération Fail-Fast de la clé maître
        master_key_str = os.environ.get("WORKFLOW_MASTER_KEY")
        if not master_key_str:
            raise engine_errors.N8nLifeEngineError(
                "La variable d'environnement WORKFLOW_MASTER_KEY est manquante.",
                error_code="ERR_VAULT_MISSING_MASTER_KEY"
            )
        
        # ---------------------------------------------------------
        # DERIVATION HKDF (Standard robuste long-terme)
        # ---------------------------------------------------------
        hkdf_enc = HKDF(
            algorithm=hashes.SHA256(),
            length=32, # AES-256 requiert 32 bytes
            salt=None,
            info=b"ENC_KEY_DERIVATION"
        )
        self._enc_key = hkdf_enc.derive(master_key_str.encode('utf-8'))

        hkdf_mac = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"MAC_KEY_DERIVATION"
        )
        self._mac_key = hkdf_mac.derive(master_key_str.encode('utf-8'))


    def encrypt(self, raw_secret_dict: Dict[str, Any]) -> str:
        """
        Chiffre un secret. Stratégie : Encrypt-then-MAC.
        """
        try:
            # 1. JSON Déterministe : Tri des clés et suppression des espaces inutiles
            raw_bytes = json.dumps(
                raw_secret_dict, 
                separators=(',', ':'), 
                sort_keys=True
            ).encode('utf-8')
            
            # 2. Padding PKCS7
            padder = padding.PKCS7(algorithms.AES.block_size).padder()
            padded_data = padder.update(raw_bytes) + padder.finalize()

            # 3. Chiffrement AES-256-CBC
            iv = os.urandom(16)
            cipher = Cipher(algorithms.AES(self._enc_key), modes.CBC(iv))
            encryptor = cipher.encryptor()
            ciphertext = encryptor.update(padded_data) + encryptor.finalize()

            # 4. Signature HMAC sur "IV + Ciphertext"
            h = HMAC(self._mac_key, hashes.SHA256())
            h.update(iv + ciphertext)
            mac = h.finalize()

            # 5. Formatage final du Blob
            return "$".join([
                f"v{self.CURRENT_CRYPTO_VERSION}",
                base64.b64encode(iv).decode('utf-8'),
                base64.b64encode(ciphertext).decode('utf-8'),
                base64.b64encode(mac).decode('utf-8')
            ])

        except Exception as e:
            raise engine_errors.N8nLifeEngineError(
                "Échec du chiffrement du secret.",
                error_code="ERR_CRYPTO_ENCRYPT_FAILED",
                details={"technical_error": str(e)}
            )

    def decrypt(self, encrypted_blob: str) -> Dict[str, Any]:
        """
        Déchiffrement JIT. Vérifie le HMAC avant de déchiffrer.
        """
        try:
            parts = encrypted_blob.split('$')
            if len(parts) != 4:
                raise ValueError("Format de blob invalide ou corrompu.")

            version_str, b64_iv, b64_ciphertext, b64_mac = parts
            
            if version_str != f"v{self.CURRENT_CRYPTO_VERSION}":
                raise ValueError(f"Version crypto non supportée : {version_str}")

            iv = base64.b64decode(b64_iv)
            ciphertext = base64.b64decode(b64_ciphertext)
            expected_mac = base64.b64decode(b64_mac)

            # 1. Vérification d'intégrité (HMAC) AVANT déchiffrement
            h = HMAC(self._mac_key, hashes.SHA256())
            h.update(iv + ciphertext)
            try:
                h.verify(expected_mac)
            except Exception:
                raise engine_errors.N8nLifeEngineError(
                    "Intégrité compromise. Le secret a été altéré.",
                    error_code="ERR_CRYPTO_INTEGRITY_FAILED"
                )

            # 2. Déchiffrement AES
            cipher = Cipher(algorithms.AES(self._enc_key), modes.CBC(iv))
            decryptor = cipher.decryptor()
            padded_data = decryptor.update(ciphertext) + decryptor.finalize()

            # 3. Unpadding
            unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
            raw_bytes = unpadder.update(padded_data) + unpadder.finalize()

            # 4. JSON Loads
            return json.loads(raw_bytes.decode('utf-8'))

        except engine_errors.N8nLifeEngineError:
            raise
        except Exception as e:
            raise engine_errors.N8nLifeEngineError(
                "Échec du déchiffrement : format ou clé invalide.",
                error_code="ERR_CRYPTO_DECRYPT_FAILED",
                details={"technical_error": str(e)}
            )