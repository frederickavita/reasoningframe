# -*- coding: utf-8 -*-
# applications/n8n_life/controllers/test_security.py

import os
import copy
import time
import hmac
import hashlib
import importlib

# Imports avec reload (Namespace n8n_life)
import applications.reasoningframe.modules.engine.errors as engine_errors
import applications.reasoningframe.modules.security.sanitizer as sec_sanitizer
import applications.reasoningframe.modules.security.vault as sec_vault
import applications.reasoningframe.modules.security.expressions as sec_expr
import applications.reasoningframe.modules.security.validators as sec_valid

importlib.reload(engine_errors)
importlib.reload(sec_sanitizer)
importlib.reload(sec_vault)
importlib.reload(sec_expr)
importlib.reload(sec_valid)

def run_all():
    """Point d'entrée pour lancer toute la suite de tests de sécurité."""
    results = {
        "1_sanitizer": test_sanitizer(),
        "2_vault": test_vault(),
        "3_expressions": test_expressions(),
        "4_validators": test_validators()
    }
    return response.json(results)

# =========================================================================
# 1. TESTS DU SANITIZER (Déjà validés)
# =========================================================================
def test_sanitizer():
    res = {}
    sanitizer = sec_sanitizer.PayloadSanitizer
    original_payload = {"Stripe-Api-Secret": "sk_live_12345", "nested": {"user_password": "my_password"}}
    clean_payload = sanitizer.sanitize(original_payload)
    res["1A_keys_and_immutability"] = (clean_payload["Stripe-Api-Secret"] == "[REDACTED]" and original_payload["Stripe-Api-Secret"] == "sk_live_12345")
    url_test = sanitizer.sanitize("Erreur sur https://admin:supersecret@api.com/v1")
    res["1B_strings_and_urls"] = ("admin" not in url_test and "supersecret" not in url_test)
    class BizarreObject: pass
    bizarre_dict = {"data": BizarreObject()}
    res["1C_failsafe"] = isinstance(sanitizer.sanitize(bizarre_dict), (dict, str)) 
    return res

# =========================================================================
# 2. TESTS DU VAULT (Déjà validés)
# =========================================================================
def test_vault():
    res = {}
    old_key = os.environ.get("WORKFLOW_MASTER_KEY")
    os.environ["WORKFLOW_MASTER_KEY"] = "super_secret_master_key_for_testing_purposes_only!"
    vault = sec_vault.CredentialVault()
    secret_data = {"api_key": "sk_test_999"}
    blob1 = vault.encrypt(secret_data)
    res["2A_encrypt_decrypt"] = (vault.decrypt(blob1) == secret_data)
    blob2 = vault.encrypt(secret_data)
    res["2B_random_iv"] = (blob1 != blob2)
    try:
        vault.decrypt(blob1[:-1] + ("X" if blob1[-1] != "X" else "Y"))
        res["2C_integrity_check"] = False
    except engine_errors.N8nLifeEngineError:
        res["2C_integrity_check"] = True
    if old_key: os.environ["WORKFLOW_MASTER_KEY"] = old_key
    return res

# =========================================================================
# 3. TESTS DU PARSER D'EXPRESSIONS
# =========================================================================
class MockItem:
    def __init__(self, data):
        self.json = data

class MockContext:
    def __init__(self):
        self.outputs = {
            "trigger": [MockItem({"user_id": 42, "amount": 100.5})],
        }
    def get_node_output(self, node_id):
        if node_id not in self.outputs:
            raise engine_errors.NodeOutputNotFoundError(node_id)
        return self.outputs[node_id]

def test_expressions():
    res = {}
    parser = sec_expr.ExpressionParser
    ctx = MockContext()
    current_item = MockItem({"name": "Alice"})

    # 3A : Résolution basique de l'historique (steps.*)
    val_steps = parser.resolve("{{ steps.trigger.json.user_id }}", ctx)
    res["3A_resolve_steps"] = (val_steps == 42) # Doit garder le type Int !

    # 3B : Résolution de l'item courant (current.*)
    val_current = parser.resolve("{{ current.json.name }}", ctx, current_item)
    res["3B_resolve_current"] = (val_current == "Alice")

    # 3C : Interpolation mixte de strings
    val_mixed = parser.resolve("ID: {{ steps.trigger.json.user_id }} - Nom: {{ current.json.name }}", ctx, current_item)
    res["3C_mixed_interpolation"] = (val_mixed == "ID: 42 - Nom: Alice")

    # 3D : Fail-Fast sur chemin introuvable
    try:
        parser.resolve("{{ steps.trigger.json.fake_key }}", ctx)
        res["3D_fail_missing_key"] = False
    except engine_errors.ExpressionEvaluationError:
        res["3D_fail_missing_key"] = True

    # 3E : Fail-Fast sur nœud non exécuté
    try:
        parser.resolve("{{ steps.ghost_node.json.data }}", ctx)
        res["3E_fail_ghost_node"] = False
    except engine_errors.ExpressionEvaluationError as e:
        # Doit encapsuler proprement le NodeOutputNotFoundError
        res["3E_fail_ghost_node"] = ("ghost_node" in str(e))

    return res

# =========================================================================
# 4. TESTS DES VALIDATEURS DE WEBHOOK
# =========================================================================
def test_validators():
    res = {}
    validator = sec_valid.WebhookValidator
    secret = "my_webhook_secret"
    body = b'{"event": "payment_success"}'
    
    # Préparation d'une signature Custom valide
    mac_custom = hmac.new(secret.encode('utf-8'), msg=body, digestmod=hashlib.sha256)
    valid_custom_sig = mac_custom.hexdigest()

    # 4A : Custom HMAC - Succès
    try:
        validator.validate(
            raw_body=body, 
            headers={"x-signature": valid_custom_sig}, 
            shared_secret=secret, 
            strategy="custom_hmac", 
            signature_header_key="x-signature"
        )
        res["4A_custom_hmac_success"] = True
    except engine_errors.WebhookValidationError:
        res["4A_custom_hmac_success"] = False

    # 4B : Custom HMAC - Rejet d'une mauvaise signature (inclut préfixe sha256= simulé)
    try:
        validator.validate(body, {"x-sig": "sha256=BAD_SIG"}, secret, "custom_hmac", "x-sig")
        res["4B_custom_hmac_reject_bad"] = False
    except engine_errors.WebhookValidationError:
        res["4B_custom_hmac_reject_bad"] = True

    # Préparation d'une signature Stripe valide
    t = int(time.time())
    stripe_payload = f"{t}.".encode('utf-8') + body
    mac_stripe = hmac.new(secret.encode('utf-8'), msg=stripe_payload, digestmod=hashlib.sha256)
    valid_stripe_header = f"t={t},v1={mac_stripe.hexdigest()},v1=old_bad_signature" # Test du secret rollover

    # 4C : Stripe HMAC - Succès (Supporte signatures multiples v1=)
    try:
        validator.validate(body, {"Stripe-Signature": valid_stripe_header}, secret, "stripe_hmac")
        res["4C_stripe_hmac_success"] = True
    except engine_errors.WebhookValidationError as e:
        res["4C_stripe_hmac_success"] = str(e) # Affichera l'erreur si ça rate

    # 4D : Stripe HMAC - Rejet Timeout (Replay Attack)
    old_t = int(time.time()) - 600 # 10 minutes dans le passé (tolérance = 5 min)
    bad_stripe_payload = f"{old_t}.".encode('utf-8') + body
    bad_mac_stripe = hmac.new(secret.encode('utf-8'), msg=bad_stripe_payload, digestmod=hashlib.sha256)
    expired_stripe_header = f"t={old_t},v1={bad_mac_stripe.hexdigest()}"
    
    try:
        validator.validate(body, {"Stripe-Signature": expired_stripe_header}, secret, "stripe_hmac")
        res["4D_stripe_replay_attack_rejected"] = False
    except engine_errors.WebhookValidationError as e:
        res["4D_stripe_replay_attack_rejected"] = ("expiré" in str(e).lower() or "replay" in str(e).lower())

    return res