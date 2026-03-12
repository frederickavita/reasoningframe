# -*- coding: utf-8 -*-
# applications/n8n_life/modules/services/execution_service.py

import importlib
import datetime
from typing import Dict, Any, Optional

# Imports stricts alignés sur l'architecture validée
import applications.reasoningframe.modules.nodes.base as nodes_base
import applications.reasoningframe.modules.engine.factory as engine_factory
import applications.reasoningframe.modules.engine.runner as engine_runner
import applications.reasoningframe.modules.engine.errors as engine_errors
import applications.reasoningframe.modules.services.credential_service as serv_credential
import applications.reasoningframe.modules.helpers.http_helper as helper_http
import applications.reasoningframe.modules.security.sanitizer as sec_sanitizer
import applications.reasoningframe.modules.nodes.registry as nodes_registry

importlib.reload(nodes_base)
importlib.reload(engine_factory)
importlib.reload(engine_runner)
importlib.reload(engine_errors)
importlib.reload(serv_credential)
importlib.reload(helper_http)
importlib.reload(sec_sanitizer)
importlib.reload(nodes_registry)

class ExecutionService:
    """
    Orchestrateur principal d'un run applicatif.
    Fait le pont exact entre le DAL et le moteur d'exécution.
    """

    def __init__(self, db: Any, user_id: int):
        self.db = db
        self.user_id = user_id
        self.credential_service = serv_credential.CredentialService(db=self.db, user_id=self.user_id)
        self.http_helper = helper_http.HttpHelper()

    def execute_workflow(self, 
                         user_workflow_id: int, 
                         trigger_node_id: Optional[str] = None, 
                         trigger_payload: Optional[Dict[str, Any]] = None,
                         trigger_type: str = "manual",
                         started_by: str = "user",
                         source_event_id: Optional[str] = None) -> Dict[str, Any]:
        
        # =====================================================================
        # 1. VÉRIFICATIONS MÉTIER & DAL STRICTES (Sécurité d'abord)
        # =====================================================================
        workflow_record = self.db(
            (self.db.user_workflow.id == user_workflow_id) & 
            (self.db.user_workflow.user_id == self.user_id)
        ).select().first()

        if not workflow_record:
            raise engine_errors.N8nLifeEngineError("Workflow introuvable ou accès refusé.", "ERR_WORKFLOW_NOT_FOUND")

        if not workflow_record.is_legitimately_acquired:
            raise engine_errors.N8nLifeEngineError("Workflow non acquis légitimement.", "ERR_WORKFLOW_ILLEGITIMATE")

        if workflow_record.desired_state != 'ON':
            raise engine_errors.N8nLifeEngineError(f"Le workflow n'est pas activé (desired_state: {workflow_record.desired_state}).", "ERR_WORKFLOW_INACTIVE")

        safe_runtime_status = getattr(workflow_record, 'runtime_status', 'ready').lower()
        if safe_runtime_status not in ('ready', 'active'):
            raise engine_errors.N8nLifeEngineError(f"Le workflow n'est pas prêt (runtime_status: {safe_runtime_status}).", "ERR_WORKFLOW_NOT_READY")

        # =====================================================================
        # 1.bis IDEMPOTENCE (Après vérification des droits !)
        # =====================================================================
        if source_event_id:
            existing_run = self.db(
                (self.db.workflow_run.source_event_id == source_event_id) & 
                (self.db.workflow_run.user_workflow_id == user_workflow_id)
            ).select(self.db.workflow_run.id, self.db.workflow_run.status).first()
            
            if existing_run:
                return {
                    "run_id": existing_run.id,
                    "status": existing_run.status,
                    "message": "Exécution ignorée (Idempotence : source_event_id déjà traité)."
                }

        # =====================================================================
        # 2. PRÉPARATION DU MOTEUR
        # =====================================================================
        wf_def = engine_factory.WorkflowFactory.build_workflow(workflow_record.workflow_json)

        actual_trigger_id = trigger_node_id or self._find_trigger_node_id(wf_def)
        if not actual_trigger_id:
            raise engine_errors.N8nLifeEngineError("Impossible de déterminer un nœud de départ (Trigger) valide.", "ERR_TRIGGER_NOT_FOUND")

        runner = engine_runner.ExecutionEngine(
            node_registry=nodes_registry.NodeRegistry,
            security_provider=self.credential_service,
            http_helper=self.http_helper
        )

        # =====================================================================
        # 3. CRÉATION DU RUN EN BASE
        # =====================================================================
        start_time = datetime.datetime.now()
        safe_payload_snapshot = sec_sanitizer.PayloadSanitizer.sanitize(trigger_payload or {})
        
        run_id = self.db.workflow_run.insert(
            user_workflow_id=user_workflow_id,
            trigger_type=trigger_type,
            started_by=started_by,
            source_event_id=source_event_id,
            status='running',
            error_code=None,
            trigger_payload_snapshot=safe_payload_snapshot,
            started_at=start_time,
            finished_at=None
        )

        # =====================================================================
        # 4. EXÉCUTION & LECTURE DU STATUT
        # =====================================================================
        run_status = "success"
        final_error_code = None
        error_details_dump = None
        final_context = None

        try:
            final_context = runner.run(
                wf_def=wf_def,
                trigger_node_id=actual_trigger_id,
                trigger_payload=trigger_payload or {}
            )
            
            if getattr(final_context, 'run_state', 'success') == 'failed':
                run_status = "failed"
                errors_list = getattr(final_context, 'errors', [])
                if errors_list and isinstance(errors_list, list) and isinstance(errors_list[0], dict):
                    final_error_code = errors_list[0].get('error_code', 'ERR_STEP_FAILED')
                    error_details_dump = {
                        "message": "Échec d'une étape", 
                        "details": sec_sanitizer.PayloadSanitizer.sanitize(errors_list)
                    }
                else:
                    final_error_code = "ERR_UNKNOWN_FAIL"
                    error_details_dump = {"message": "Le workflow a échoué sans fournir de détails."}

        except engine_errors.N8nLifeEngineError as e:
            run_status = "failed"
            final_error_code = e.error_code
            error_details_dump = {"message": str(e), "details": sec_sanitizer.PayloadSanitizer.sanitize(getattr(e, 'details', {}))}
        except Exception as e:
            run_status = "failed"
            final_error_code = "ERR_SYSTEM_CRASH"
            error_details_dump = {"message": f"Erreur critique inattendue : {str(e)}"}

        # =====================================================================
        # 5. PERSISTANCE DES RÉSULTATS
        # =====================================================================
        end_time = datetime.datetime.now()

        update_data = {
            "status": run_status,
            "finished_at": end_time,
            "error_code": final_error_code
        }
        
        if 'error_details' in self.db.workflow_run.fields:
            update_data['error_details'] = error_details_dump

        self.db(self.db.workflow_run.id == run_id).update(**update_data)

        output_items_count = 0
        
        if final_context and hasattr(final_context, 'step_history'):
            for i, step in enumerate(final_context.step_history):
                is_dict = isinstance(step, dict)
                
                step_exec_order = step.get('execution_order') if is_dict else getattr(step, 'execution_order', i + 1)
                step_node_id = step.get('node_id') if is_dict else getattr(step, 'node_id', 'unknown')
                step_node_type = step.get('node_type') if is_dict else getattr(step, 'node_type', 'unknown')
                step_status = step.get('status') if is_dict else getattr(step, 'status', 'success')
                step_error_code = step.get('error_code') if is_dict else getattr(step, 'error_code', None)
                step_error_msg = step.get('error_message') if is_dict else getattr(step, 'error_message', None)
                step_in_count = step.get('input_count') if is_dict else getattr(step, 'input_count', 0)
                step_out_count = step.get('output_count') if is_dict else getattr(step, 'output_count', 0)
                
                # CORRECTION : Fallback réel (or start_time/end_time) si la valeur lue est None
                raw_start = step.get('started_at') if is_dict else getattr(step, 'started_at', None)
                step_start = raw_start or start_time
                
                raw_finish = step.get('finished_at') if is_dict else getattr(step, 'finished_at', None)
                step_finish = raw_finish or end_time
                
                step_time_ms = step.get('execution_time_ms') if is_dict else getattr(step, 'execution_time_ms', 0)
                
                step_snapshot = None
                if hasattr(final_context, 'node_outputs') and step_node_id in final_context.node_outputs:
                    items = final_context.node_outputs[step_node_id]
                    step_snapshot = sec_sanitizer.PayloadSanitizer.sanitize([item.json for item in items])
                    output_items_count = len(items)

                self.db.workflow_run_step.insert(
                    run_id=run_id,
                    execution_order=step_exec_order,
                    node_id=step_node_id,
                    node_type=step_node_type,
                    status=step_status,
                    error_code=step_error_code,
                    error_message=step_error_msg,
                    input_count=step_in_count,
                    output_count=step_out_count,
                    context_snapshot=step_snapshot,
                    started_at=step_start,
                    finished_at=step_finish,
                    execution_time_ms=step_time_ms
                )

        # =====================================================================
        # 6. RETOUR
        # =====================================================================
        return {
            "run_id": run_id,
            "status": run_status,
            "duration_ms": int((end_time - start_time).total_seconds() * 1000),
            "output_items_count": output_items_count,
            "error_code": final_error_code,
            "error_details": error_details_dump
        }

    # CORRECTION : Annotation pointant sur le bon namespace (nodes_base)
    def _find_trigger_node_id(self, wf_def: nodes_base.WorkflowDefinition) -> Optional[str]:
        for node_id, node in wf_def.nodes.items():
            if node.type.startswith("trigger."):
                return node_id
        return None