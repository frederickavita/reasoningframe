# -*- coding: utf-8 -*-
# applications/n8n_life/modules/services/workflow_service.py

import importlib
from typing import Dict, Any, List, Optional

import applications.reasoningframe.modules.engine.factory as engine_factory
import applications.reasoningframe.modules.engine.graph_validator as graph_validator
import applications.reasoningframe.modules.engine.errors as engine_errors
import applications.reasoningframe.modules.services.credential_service as serv_credential

importlib.reload(engine_factory)
importlib.reload(graph_validator)
importlib.reload(engine_errors)
importlib.reload(serv_credential)

class WorkflowService:
    """
    Gestionnaire métier du cycle de vie d'un workflow.
    Garantit l'isolation B2B, valide les graphes, autorise les brouillons structurels et gère l'état technique.
    """

    def __init__(self, db: Any, user_id: int, credential_service: Optional[Any] = None):
        self.db = db
        self.user_id = user_id
        self.credential_service = credential_service or serv_credential.CredentialService(db=self.db, user_id=self.user_id)

    # =========================================================================
    # LECTURE & ISOLATION
    # =========================================================================

    def load_workflow(self, user_workflow_id: int) -> Any:
        row = self.db(
            (self.db.user_workflow.id == user_workflow_id) & 
            (self.db.user_workflow.user_id == self.user_id)
        ).select().first()

        if not row:
            raise engine_errors.N8nLifeEngineError(
                message=f"Workflow #{user_workflow_id} introuvable ou accès refusé.",
                error_code="ERR_WORKFLOW_NOT_FOUND"
            )
        return row

    def export_workflow_json(self, user_workflow_id: int) -> Dict[str, Any]:
        wf = self.load_workflow(user_workflow_id)
        return {
            "id": wf.id,
            "name": wf.name,
            "workflow_json": wf.workflow_json,
            "template_id": getattr(wf, 'template_id', None),
            "template_version_at_clone": getattr(wf, 'template_version_at_clone', None)
        }

    # =========================================================================
    # VALIDATION TECHNIQUE
    # =========================================================================

    def validate_workflow_json(self, workflow_json: Dict[str, Any]) -> Dict[str, Any]:
        if not workflow_json or not isinstance(workflow_json, dict):
            raise engine_errors.N8nLifeEngineError("Le JSON du workflow est invalide ou vide.", "ERR_WORKFLOW_INVALID_JSON")

        try:
            wf_def = engine_factory.WorkflowFactory.build_workflow(workflow_json)
            graph_validator.GraphValidator.validate(wf_def)
            
            return {
                "is_valid": True,
                "node_count": len(wf_def.nodes)
            }
        except engine_errors.N8nLifeEngineError as e:
            raise engine_errors.N8nLifeEngineError(f"Graphe invalide : {str(e)}", "ERR_WORKFLOW_GRAPH_INVALID", details=getattr(e, 'details', {}))
        # Les vraies erreurs inattendues (ex: TypeError) remonteront naturellement ici pour le debug

    def extract_required_credentials(self, workflow_json: Dict[str, Any]) -> List[str]:
        if not workflow_json or not isinstance(workflow_json, dict):
            return []
            
        try:
            wf_def = engine_factory.WorkflowFactory.build_workflow(workflow_json)
            required = {node.credential_key for node in wf_def.nodes.values() if getattr(node, 'credential_key', None)}
            return sorted(list(required))
        except engine_errors.N8nLifeEngineError:
            # CORRECTION : On attrape uniquement les erreurs métier (ex: type de nœud inconnu) 
            # pour renvoyer [] en mode brouillon. Un vrai bug Python fera crasher proprement.
            return []

    def check_workflow_completeness(self, user_workflow_id: int, wf_record: Optional[Any] = None) -> Dict[str, Any]:
        wf = wf_record or self.load_workflow(user_workflow_id)
        
        if not wf.workflow_json or not isinstance(wf.workflow_json, dict):
            return {
                "is_complete": False, "graph_valid": False, 
                "missing_credentials": [], "required_credentials": [], "errors": ["JSON manquant ou format invalide"]
            }

        graph_valid = False
        errors = []
        try:
            self.validate_workflow_json(wf.workflow_json)
            graph_valid = True
        except engine_errors.N8nLifeEngineError as e:
            errors.append(str(e))

        required_creds = self.extract_required_credentials(wf.workflow_json) if graph_valid else []
        missing_creds = [cred for cred in required_creds if not self.credential_service.check_credential_exists(cred)]

        is_complete = graph_valid and (len(missing_creds) == 0)

        return {
            "is_complete": is_complete,
            "graph_valid": graph_valid,
            "missing_credentials": missing_creds,
            "required_credentials": required_creds,
            "errors": errors
        }

    # =========================================================================
    # CYCLE DE VIE & ÉTATS
    # =========================================================================

    def refresh_workflow_status(self, user_workflow_id: int) -> str:
        wf = self.load_workflow(user_workflow_id)
        
        if wf.runtime_status == 'archived':
            return 'archived'

        comp = self.check_workflow_completeness(user_workflow_id, wf_record=wf)
        
        if not comp["graph_valid"]:
            new_status = 'error'
        elif comp["missing_credentials"]:
            new_status = 'waiting_credentials'
        else:
            if wf.desired_state == 'ON':
                new_status = 'active'
            else:
                new_status = 'ready'

        self.db(self.db.user_workflow.id == user_workflow_id).update(runtime_status=new_status)
        return new_status

    # =========================================================================
    # ACTIONS CRUD
    # =========================================================================

    def create_workflow(self, name: str, workflow_json: Optional[Dict[str, Any]] = None, template_id: Optional[int] = None, template_version_at_clone: Optional[int] = None, is_legitimately_acquired: bool = True) -> Any:
        if not name or not name.strip():
            raise engine_errors.N8nLifeEngineError("Le nom du workflow est requis.", "ERR_WORKFLOW_INVALID_NAME")

        safe_json = workflow_json or {"nodes": [], "connections": {}}

        wf_id = self.db.user_workflow.insert(
            user_id=self.user_id,
            name=name,
            workflow_json=safe_json,
            template_id=template_id,
            template_version_at_clone=template_version_at_clone,
            desired_state='OFF',
            runtime_status='error', 
            is_legitimately_acquired=is_legitimately_acquired 
        )
        
        self.refresh_workflow_status(wf_id)
        return self.load_workflow(wf_id)

    def import_workflow_json(self, user_workflow_id: int, workflow_json: Dict[str, Any]) -> Dict[str, Any]:
        wf = self.load_workflow(user_workflow_id)
        
        if wf.runtime_status == 'archived':
            raise engine_errors.N8nLifeEngineError("Impossible de modifier un workflow archivé.", "ERR_WORKFLOW_ARCHIVED")

        # CORRECTION : Contrat structurel minimal
        if not isinstance(workflow_json, dict):
            raise engine_errors.N8nLifeEngineError("Le format du workflow_json est invalide (doit être un dictionnaire).", "ERR_WORKFLOW_INVALID_FORMAT")

        val_res = {"is_valid": False, "errors": []}
        try:
            val_res = self.validate_workflow_json(workflow_json)
        except engine_errors.N8nLifeEngineError as e:
            val_res["is_valid"] = False
            val_res["errors"] = [str(e)]

        self.db(self.db.user_workflow.id == user_workflow_id).update(workflow_json=workflow_json)
        self.refresh_workflow_status(user_workflow_id)

        return {
            "workflow": self.load_workflow(user_workflow_id),
            "required_credentials": self.extract_required_credentials(workflow_json),
            "validation": val_res
        }

    # =========================================================================
    # ACTIONS INTENTIONNELLES (ON / OFF / ARCHIVE)
    # =========================================================================

    def activate_workflow(self, user_workflow_id: int) -> Any:
        wf = self.load_workflow(user_workflow_id)
        
        if wf.runtime_status == 'archived':
            raise engine_errors.N8nLifeEngineError("Impossible d'activer un workflow archivé.", "ERR_WORKFLOW_ARCHIVED")

        comp = self.check_workflow_completeness(user_workflow_id, wf_record=wf)
        if not comp["is_complete"]:
            error_details = comp["errors"] if not comp["graph_valid"] else f"Credentials manquants: {comp['missing_credentials']}"
            raise engine_errors.N8nLifeEngineError(
                f"Le workflow est incomplet et ne peut être activé. ({error_details})", 
                "ERR_WORKFLOW_INCOMPLETE"
            )

        self.db(self.db.user_workflow.id == user_workflow_id).update(desired_state='ON')
        self.refresh_workflow_status(user_workflow_id)
        
        return self.load_workflow(user_workflow_id)

    def deactivate_workflow(self, user_workflow_id: int) -> Any:
        self.load_workflow(user_workflow_id)
        self.db(self.db.user_workflow.id == user_workflow_id).update(desired_state='OFF')
        self.refresh_workflow_status(user_workflow_id)
        return self.load_workflow(user_workflow_id)

    def archive_workflow(self, user_workflow_id: int) -> Any:
        self.load_workflow(user_workflow_id)
        self.db(self.db.user_workflow.id == user_workflow_id).update(
            desired_state='OFF',
            runtime_status='archived'
        )
        return self.load_workflow(user_workflow_id)