# -*- coding: utf-8 -*-
# applications/n8n_life/modules/services/webhook_service.py

import json
import importlib
from typing import Dict, Any, Optional, Tuple

import applications.reasoningframe.modules.engine.factory as engine_factory
import applications.reasoningframe.modules.engine.errors as engine_errors
import applications.reasoningframe.modules.services.workflow_service as serv_workflow
import applications.reasoningframe.modules.services.execution_service as serv_execution
import applications.reasoningframe.modules.services.credential_service as serv_credential
import applications.reasoningframe.modules.security.validators as sec_validators
import applications.reasoningframe.modules.nodes.base as nodes_base

importlib.reload(engine_factory)
importlib.reload(engine_errors)
importlib.reload(serv_workflow)
importlib.reload(serv_execution)
importlib.reload(serv_credential)
importlib.reload(sec_validators)
importlib.reload(nodes_base)

class WebhookService:
    """
    Portier sécurisé. Résout l'endpoint, vérifie le propriétaire via le workflow,
    valide la signature et délègue l'exécution au moteur.
    """

    def __init__(self, db: Any, 
                 workflow_service: Optional[Any] = None, 
                 execution_service: Optional[Any] = None, 
                 credential_service: Optional[Any] = None):
        self.db = db
        self.workflow_service = workflow_service
        self.execution_service = execution_service
        self.credential_service = credential_service

    # =========================================================================
    # RÉSOLUTION D'ENDPOINT (Priorité Exacte > ANY)
    # =========================================================================

    def load_endpoint(self, path: str, method: str) -> Any:
        norm_method = method.upper()
        
        # On récupère tous les candidats potentiels sur ce chemin
        rows = self.db(
            (self.db.webhook_endpoint.path == path) & 
            ((self.db.webhook_endpoint.http_method == norm_method) | 
             (self.db.webhook_endpoint.http_method == 'ANY'))
        ).select()

        if not rows:
            raise engine_errors.N8nLifeEngineError(f"Endpoint {norm_method} {path} inconnu.", "ERR_WEBHOOK_NOT_FOUND")

        # Règle de priorité : la méthode exacte bat le joker 'ANY'
        exact_match = next((r for r in rows if r.http_method == norm_method), None)
        endpoint = exact_match if exact_match else rows[0]

        if not endpoint.is_active:
            raise engine_errors.N8nLifeEngineError("Endpoint désactivé.", "ERR_WEBHOOK_INACTIVE")
            
        return endpoint

    # =========================================================================
    # CHARGEMENT DU WORKFLOW (Pivot de user_id)
    # =========================================================================

    def load_target_workflow(self, endpoint: Any) -> Any:
        """Charge le workflow et valide ses états sans dépendre d'un service externe."""
        wf = self.db.user_workflow(endpoint.user_workflow_id)
        
        if not wf:
            raise engine_errors.N8nLifeEngineError("Workflow lié introuvable.", "ERR_WORKFLOW_NOT_FOUND")
            
        # Validation métier Fail-Fast (Isolation et État)
        if wf.desired_state != 'ON':
            raise engine_errors.N8nLifeEngineError("Workflow désactivé (OFF).", "ERR_WORKFLOW_INACTIVE")
            
        if wf.runtime_status not in ('ready', 'active'):
            raise engine_errors.N8nLifeEngineError(f"Workflow non prêt ({wf.runtime_status}).", "ERR_WORKFLOW_NOT_READY")
            
        if not wf.is_legitimately_acquired:
            raise engine_errors.N8nLifeEngineError("Acquisition non légitime.", "ERR_WORKFLOW_ILLEGITIMATE")
            
        return wf

    def load_trigger_definition(self, workflow_record: Any, trigger_node_id: str) -> Tuple[nodes_base.WorkflowDefinition, Any]:
        """Vérifie l'existence du trigger dans le JSON."""
        wf_def = engine_factory.WorkflowFactory.build_workflow(workflow_record.workflow_json)
        trigger_node = wf_def.nodes.get(trigger_node_id)
        
        if not trigger_node:
            raise engine_errors.N8nLifeEngineError(f"Trigger {trigger_node_id} absent du JSON.", "ERR_TRIGGER_NOT_FOUND")
            
        if not trigger_node.type.startswith("trigger."):
            raise engine_errors.N8nLifeEngineError(f"Le nœud {trigger_node_id} n'est pas un trigger.", "ERR_INVALID_TRIGGER")
            
        return wf_def, trigger_node

    # =========================================================================
    # SÉCURITÉ & SIGNATURE
    # =========================================================================

    def resolve_signature_requirements(self, endpoint: Any, trigger_node: Any, owner_id: int) -> Tuple[str, Optional[str], Optional[str]]:
        """Détermine la stratégie et récupère le secret de signature."""
        strategy = endpoint.signature_strategy or 'none'
        
        if strategy not in ('none', 'custom_hmac', 'stripe_hmac'):
            raise engine_errors.N8nLifeEngineError(f"Stratégie inconnue : {strategy}", "ERR_WEBHOOK_BAD_STRATEGY")

        if strategy == 'none':
            return strategy, None, None

        cred_serv = self.credential_service or serv_credential.CredentialService(self.db, owner_id)
        shared_secret = None
        
        if trigger_node.credential_key:
            creds = cred_serv.get_decrypted_secret(trigger_node.credential_key)
            # CORRECTION : Traitement défensif si le secret n'est pas un dictionnaire
            if isinstance(creds, dict):
                shared_secret = creds.get('signing_secret')
            else:
                # Si le format est inattendu (ex: string brute), on fail-fast
                raise engine_errors.N8nLifeEngineError("Format de credential invalide (dict attendu).", "ERR_WEBHOOK_BAD_CREDENTIAL_FORMAT")

        if not shared_secret:
            raise engine_errors.N8nLifeEngineError("Secret HMAC introuvable.", "ERR_WEBHOOK_MISSING_SECRET")

        signature_header_key = trigger_node.parameters.get('signature_header_key') if strategy == 'custom_hmac' else None
        return strategy, shared_secret, signature_header_key

    # =========================================================================
    # PAYLOAD & IDEMPOTENCE
    # =========================================================================

    def parse_initial_payload(self, raw_body: bytes, headers: Dict[str, Any], method: str, query_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Normalise les headers et parse le corps de la requête."""
        low_headers = {k.lower(): v for k, v in headers.items()}
        content_type = low_headers.get('content-type', '').lower()
        parsed_body = {}

        if 'application/json' in content_type and raw_body:
            try:
                parsed_body = json.loads(raw_body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                parsed_body = {"_raw_text": raw_body.decode("utf-8", errors="replace")}
        elif raw_body:
            parsed_body = {"_raw_text": raw_body.decode("utf-8", errors="replace")}

        return {
            "headers": low_headers,
            "query_params": query_params or {},
            "body": parsed_body,
            "meta": {
                "content_type": content_type,
                "received_via": "webhook",
                "method": method.upper()
            }
        }

    def extract_source_event_id(self, strategy: str, payload: Dict[str, Any], low_headers: Dict[str, Any]) -> Optional[str]:
        """Extrait l'ID unique de l'événement pour l'idempotence moteur."""
        if strategy == 'stripe_hmac':
            return payload.get('body', {}).get('id')
        
        # CORRECTION : Utilisation de x-shopify-event-id au lieu du topic (type)
        id_keys = ['x-event-id', 'x-request-id', 'x-github-delivery', 'x-shopify-event-id']
        for k in id_keys:
            if k in low_headers:
                return low_headers[k]
        return None

    # =========================================================================
    # ORCHESTRATION (handle_incoming_webhook)
    # =========================================================================

    def handle_incoming_webhook(self, path: str, method: str, headers: Dict[str, Any], raw_body: bytes, query_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # 1. Résolution Endpoint & Workflow (Pivot user_id)
        endpoint = self.load_endpoint(path, method)
        wf_record = self.load_target_workflow(endpoint)
        owner_id = wf_record.user_id

        # 2. Trigger & Sécurité Signature
        wf_def, trigger_node = self.load_trigger_definition(wf_record, endpoint.trigger_node_id)
        strategy, secret, h_key = self.resolve_signature_requirements(endpoint, trigger_node, owner_id)
        
        # 3. Validation HMAC (Délégation au module security)
        sec_validators.WebhookValidator.validate(raw_body, headers, secret, strategy, h_key)
        
        # 4. Parsing Payload & Extraction Idempotence
        trigger_payload = self.parse_initial_payload(raw_body, headers, method, query_params)
        source_id = self.extract_source_event_id(strategy, trigger_payload, trigger_payload['headers'])
        
        # 5. Délégation finale à l'exécution
        exec_serv = self.execution_service or serv_execution.ExecutionService(self.db, owner_id)
        
        return exec_serv.execute_workflow(
            user_workflow_id=wf_record.id,
            trigger_node_id=endpoint.trigger_node_id,
            trigger_payload=trigger_payload,
            trigger_type='webhook',
            started_by='webhook',
            source_event_id=source_id
        )