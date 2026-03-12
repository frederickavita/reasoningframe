# -*- coding: utf-8 -*-
# applications/n8n_life/modules/engine/runner.py

import time
import importlib
from enum import Enum
from typing import Dict, Any, List, Set

# =========================================================================
# IMPORTS WEB2PY (Avec mode DEV / Reload explicite)
# =========================================================================
import applications.reasoningframe.modules.engine.errors as engine_errors
importlib.reload(engine_errors)

import applications.reasoningframe.modules.engine.context as engine_context
importlib.reload(engine_context)

import applications.reasoningframe.modules.engine.item_manager as engine_item_manager
importlib.reload(engine_item_manager)

import applications.reasoningframe.modules.engine.planner as engine_planner
importlib.reload(engine_planner)

# CORRECTION 1 : Le chemin exact selon notre arborescence validée
import applications.reasoningframe.modules.nodes.base as nodes_base
importlib.reload(nodes_base)


# =========================================================================
# CONSTANTES D'ÉTAT (Enums robustes)
# =========================================================================
class RunState(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

class StepState(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped" # Anticipation pour les branches mortes du DAG


# =========================================================================
# LE MOTEUR D'EXÉCUTION
# =========================================================================
class ExecutionEngine:
    """
    Orchestrateur central du workflow (DAG-Ready).
    """
    def __init__(self, node_registry: Any, security_provider: Any, http_helper: Any):
        self.registry = node_registry
        self.security_provider = security_provider 
        self.http_helper = http_helper

    def run(self, 
            wf_def: nodes_base.WorkflowDefinition, 
            trigger_node_id: str, 
            trigger_payload: Dict[str, Any]) -> engine_context.WorkflowContext:
        
        # ---------------------------------------------------------------------
        # 1. VALIDATION STRICTE DU TRIGGER
        # ---------------------------------------------------------------------
        trigger_def = wf_def.nodes.get(trigger_node_id)
        if not trigger_def:
            raise engine_errors.GraphValidationError(f"Le nœud trigger '{trigger_node_id}' n'existe pas dans le workflow.")
        
        # Vérification explicite du contrat
        if not trigger_def.type.startswith('trigger.'):
            raise engine_errors.GraphValidationError(f"Le nœud '{trigger_node_id}' (type: {trigger_def.type}) n'est pas un trigger valide.")

        # ---------------------------------------------------------------------
        # 2. INITIALISATION DU CONTEXTE
        # ---------------------------------------------------------------------
        # CORRECTION 2 : Alignement du contrat Item
        start_item = engine_context.Item(json=trigger_payload)
        context = engine_context.WorkflowContext(trigger_items=[start_item])
        context.run_state = RunState.RUNNING.value
        
        context.update_node_output(trigger_node_id, [start_item])

        # CORRECTION 3 & 5 : Le trigger est officiellement le Step 1
        step_order = 1
        context.record_step(
            node_id=trigger_node_id,
            node_type=trigger_def.type,
            execution_order=step_order,
            status=StepState.SUCCESS.value,
            execution_time_ms=0,
            input_count=0,
            output_count=1,
            error_code=None,
            error_message=None
        )
        step_order += 1

        # ---------------------------------------------------------------------
        # 3. INITIALISATION DE LA FILE D'ATTENTE DAG
        # ---------------------------------------------------------------------
        executed_nodes: Set[str] = {trigger_node_id}
        queued_nodes: Set[str] = set()
        queue: List[str] = []

        initial_next_nodes = engine_planner.ExecutionPlanner.get_ready_successors(wf_def, trigger_node_id, executed_nodes)
        for n in initial_next_nodes:
            queue.append(n)
            queued_nodes.add(n)

        # ---------------------------------------------------------------------
        # 4. BOUCLE D'EXÉCUTION (State Machine)
        # ---------------------------------------------------------------------
        while queue and context.run_state == RunState.RUNNING.value:
            current_node_id = queue.pop(0)
            queued_nodes.remove(current_node_id)
            node_def = wf_def.nodes.get(current_node_id)
            
            step_start_time = time.time()
            step_error = None
            step_error_code = None
            outputs = []
            input_items = []

            try:
                # A. Résolution
                node_executor = self.registry.get_executor(node_def)

                # B. Reconstruction DAG des inputs
               # NOUVEAU CODE (Robuste)
                upstream_node_ids = engine_planner.ExecutionPlanner.get_upstream_nodes(wf_def, current_node_id)
                # On construit un dictionnaire couplé : { "node_1": [Item, Item], "node_2": [Item] }
                branches_data = {pid: context.get_node_output(pid) for pid in upstream_node_ids}
                # Le merge_inputs gère le Flatten et le Pairing en toute sécurité
                input_items = engine_item_manager.ItemManager.merge_inputs(branches_data)

            

                # C. Exécution
                outputs = node_executor.execute(
                    node_def=node_def,
                    input_items=input_items,
                    context=context, 
                    security_provider=self.security_provider, 
                    http_helper=self.http_helper
                )

                # D. CORRECTION 4 : Validation blindée du type de retour
                if not isinstance(outputs, list) or not all(isinstance(out, engine_context.Item) for out in outputs):
                    raise engine_errors.NodeExecutionError(current_node_id, "Contrat violé : Le nœud DOIT retourner une List[Item] valide.")

                # E. Mise à jour de l'état
                context.update_node_output(current_node_id, outputs)
                executed_nodes.add(current_node_id)

                # F. Planification DAG
                next_ready = engine_planner.ExecutionPlanner.get_ready_successors(wf_def, current_node_id, executed_nodes)
                for n in next_ready:
                    if n not in queued_nodes and n not in executed_nodes:
                        queue.append(n)
                        queued_nodes.add(n)

            except engine_errors.N8nLifeEngineError as e:
                step_error_code = getattr(e, 'error_code', 'ERR_ENGINE_KNOWN')
                step_error = str(e)
                context.halt_with_error(current_node_id, step_error_code, step_error)
                
            except Exception as e:
                step_error_code = 'ERR_INTERNAL_SYSTEM'
                step_error = f"Erreur système inattendue : {str(e)}"
                context.halt_with_error(current_node_id, step_error_code, step_error)

            finally:
                # G. Enregistrement systématique du Step (avec Error Code et Node Type)
                exec_time_ms = int((time.time() - step_start_time) * 1000)
                step_status = StepState.FAILED.value if step_error else StepState.SUCCESS.value
                
                context.record_step(
                    node_id=current_node_id,
                    node_type=node_def.type,
                    execution_order=step_order,
                    status=step_status,
                    execution_time_ms=exec_time_ms,
                    input_count=len(input_items),
                    output_count=len(outputs),
                    error_code=step_error_code,
                    error_message=step_error
                )
                step_order += 1

        # ---------------------------------------------------------------------
        # 5. CLÔTURE DU RUN
        # ---------------------------------------------------------------------
        if context.run_state == RunState.RUNNING.value:
            context.run_state = RunState.SUCCESS.value

        return context