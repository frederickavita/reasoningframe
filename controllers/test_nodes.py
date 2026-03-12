# -*- coding: utf-8 -*-
# applications/n8n_life/controllers/test_nodes.py

import importlib

# Imports au bon namespace
import applications.reasoningframe.modules.nodes.base as nodes_base
import applications.reasoningframe.modules.engine.context as engine_context
import applications.reasoningframe.modules.engine.errors as engine_errors
from applications.reasoningframe.modules.nodes.actions.http_request import HttpRequestNode

importlib.reload(nodes_base)
importlib.reload(engine_context)
importlib.reload(engine_errors)

# =========================================================================
# LES MOCKS (Faux objets pour simuler l'environnement)
# =========================================================================

class MockHttpHelper:
    def __init__(self):
        self.last_call = {}
        self.next_response = {"status_code": 200, "headers": {}, "body": {"success": True}, "request_preview": {}}
        self.should_fail = False

    def send_request(self, method, url, headers=None, query_params=None, json_body=None, data_body=None, timeout=20):
        self.last_call = {
            "method": method, "url": url, "headers": headers, 
            "query_params": query_params, "json_body": json_body
        }
        
        if self.should_fail:
            raise engine_errors.NodeExecutionError(
                node_id="HTTP_HELPER", 
                message="Timeout réseau simulé", 
                details={"request_preview": self.last_call}
            )
            
        return self.next_response

class MockSecurityProvider:
    def get_decrypted_secret(self, credential_key):
        if credential_key == "test_stripe":
            return {"Authorization": "Bearer sk_test_123"}
        return None

class MockContext(engine_context.WorkflowContext):
    def __init__(self):
        # On crée un item factice de démarrage pour satisfaire le contrat strict
        dummy_trigger = engine_context.Item(json={"source": "test_runner"})
        
        # On passe la liste d'items au constructeur parent
        super().__init__(trigger_items=[dummy_trigger])
        
        self.workflow_id = "wf_1"

# =========================================================================
# LES TESTS
# =========================================================================

def run_all():
    res = {}
    node = HttpRequestNode()
    http_mock = MockHttpHelper()
    sec_mock = MockSecurityProvider()
    ctx = MockContext()

    # ---------------------------------------------------------
    # Test 1 : Happy Path & Résolution d'Expressions
    # ---------------------------------------------------------
    item1 = engine_context.Item(json={"user_id": 42})
    def1 = nodes_base.NodeDefinition(
        node_id="node_1", 
        node_type="core.http", 
        parameters={
            "url": "https://api.com/users/{{ current.json.user_id }}",
            "method": "GET",
            "headers": {"X-Custom": "val"}
        }
    )
    
    outputs1 = node.execute(def1, [item1], ctx, sec_mock, http_mock)
    
    res["1A_url_resolved"] = (http_mock.last_call["url"] == "https://api.com/users/42")
    res["1B_output_is_item"] = isinstance(outputs1[0], engine_context.Item)
    res["1C_output_json_mapped"] = (outputs1[0].json == {"success": True})
    res["1D_meta_assigned"] = (outputs1[0].meta.get("http_status_code") == 200)

    # ---------------------------------------------------------
    # Test 2 : Injection de Secrets & Priorité locale
    # ---------------------------------------------------------
    def2 = nodes_base.NodeDefinition(
        node_id="node_2", 
        node_type="core.http", 
        credential_key="test_stripe",
        parameters={
            "url": "https://api.com/charge",
            # Le user force un header, il doit s'ajouter au secret, et s'il a le même nom, il doit gagner
            "headers": {"X-Source": "app", "Authorization": "Bearer local_override"}
        }
    )
    
    node.execute(def2, [engine_context.Item(json={})], ctx, sec_mock, http_mock)
    sent_headers = http_mock.last_call["headers"]
    
    res["2A_secret_injected"] = ("X-Source" in sent_headers)
    res["2B_local_priority"] = (sent_headers.get("Authorization") == "Bearer local_override")

    # ---------------------------------------------------------
    # Test 3 : Normalisation du Body (API renvoyant une Liste)
    # ---------------------------------------------------------
    http_mock.next_response = {"status_code": 200, "headers": {}, "body": [{"id": 1}, {"id": 2}], "request_preview": {}}
    def3 = nodes_base.NodeDefinition("node_3", "core.http", {"url": "https://api.com/list"})
    
    outputs3 = node.execute(def3, [engine_context.Item(json={})], ctx, sec_mock, http_mock)
    
    # Le nœud doit avoir encapsulé la liste dans {"data": [...]}
    res["3_list_body_encapsulated"] = (outputs3[0].json == {"data": [{"id": 1}, {"id": 2}]})

    # ---------------------------------------------------------
    # Test 4 : Fail-Fast & Repackaging d'erreur
    # ---------------------------------------------------------
   # ---------------------------------------------------------
    # Test 4 : Fail-Fast & Repackaging d'erreur
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # Test 4 : Fail-Fast & Repackaging d'erreur
    # ---------------------------------------------------------
    http_mock.should_fail = True
    def4 = nodes_base.NodeDefinition("node_4", "core.http", parameters={"url": "https://api.com/timeout"})
    
    try:
        node.execute(def4, [engine_context.Item(json={})], ctx, sec_mock, http_mock)
        res["4_error_repackaged"] = False
    except engine_errors.NodeExecutionError as e:
        # CORRECTION : Utilisation de str(e) et getattr pour être 100% safe
        safe_details = getattr(e, 'details', {})
        res["4_error_repackaged"] = (
            e.node_id == "node_4" and 
            "HTTP" in str(e) and 
            "request_preview" in safe_details
        )
    return response.json(res)