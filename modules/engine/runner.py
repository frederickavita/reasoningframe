# -*- coding: utf-8 -*-
# applications/n8n_life/modules/engine/runner.py

import importlib
import datetime
from typing import Dict, Any, List, Optional

import applications.reasoningframe.modules.engine.context as engine_context
import applications.reasoningframe.modules.engine.errors as engine_errors
import applications.reasoningframe.modules.nodes.base as nodes_base

# Rechargement pour garantir la fraîcheur en environnement web2py
importlib.reload(engine_context)
importlib.reload(engine_errors)
importlib.reload(nodes_base)

class ExecutionEngine:
    """
    Le moteur d'exécution (Runner).
    Il parcourt le graphe, instancie les nœuds via le Registry et gère le cycle de vie du Run.
    """

    def __init__(self, node_registry: Any, security_provider: Any, http_helper: Any):
        """
        Injection des dépendances cœur.
        :param node_registry: La classe ou instance NodeRegistry (doit accepter NodeDefinition).
        :param security_provider: Service capable de fournir des credentials (ex: CredentialService).
        :param http_helper: Helper pour les requêtes sortantes.
        """
        self.node_registry = node_registry
        self.security_provider = security_provider
        self.http_helper = http_helper

    def run(self, 
            wf_def: nodes_base.WorkflowDefinition, 
            trigger_node_id: str, 
            trigger_payload: Dict[str, Any]) -> engine_context.WorkflowContext:
        """
        Déclenche l'exécution d'un workflow à partir d'un trigger.
        """
        # 1. Initialisation de l'Item de départ (Payload normalisé par le WebhookService)
        start_item = engine_context.Item(json=trigger_payload)
        
        # 2. Création du contexte de run (La mémoire du workflow)
        context = engine_context.WorkflowContext(trigger_items=[start_item])
        
        # 3. Préparation de la file d'exécution (Traversal)
        # On commence par le trigger.
        queue = [trigger_node_id]
        
        # Le trigger_payload est injecté comme "donnée entrante" du premier nœud
        context.update_node_output(trigger_node_id, [start_item])

        try:
            while queue:
                current_node_id = queue.pop(0)
                
                # Exécution du nœud actuel
                output_items = self._execute_node(current_node_id, context, wf_def)
                
                # Mise à jour du contexte
                context.update_node_output(current_node_id, output_items)
                
                # Identification des successeurs
                connections = wf_def.connections.get(current_node_id, [])
                for conn in connections:
                    target_id = conn.get('target_id')
                    if target_id and target_id not in queue:
                        # On injecte les données de sortie pour le nœud suivant
                        # Note : Dans un DAG simple, le nœud suivant recevra les outputs du précédent
                        queue.append(target_id)

            context.run_state = "success"

        except engine_errors.N8nLifeEngineError as e:
            context.run_state = "failed"
            context.errors.append({
                "error_code": e.error_code,
                "message": str(e),
                "details": getattr(e, 'details', {})
            })
        except Exception as e:
            context.run_state = "failed"
            context.errors.append({
                "error_code": "ERR_INTERNAL_RUNNER",
                "message": f"Erreur critique du Runner : {str(e)}"
            })

        return context

    def _execute_node(self, node_id: str, context: engine_context.WorkflowContext, wf_def: nodes_base.WorkflowDefinition) -> List[engine_context.Item]:
        """
        Résout, instancie et exécute un nœud spécifique.
        """
        node_def = wf_def.nodes.get(node_id)
        if not node_def:
            raise engine_errors.N8nLifeEngineError(f"Nœud {node_id} introuvable dans la définition.", "ERR_NODE_NOT_FOUND")

        # --- ALIGNEMENT RÉSOLU ---
        # On passe l'objet node_def complet au Registry. 
        # Le Registry est maintenant polymorphe et gère le .type en interne.
        executor = self.node_registry.get_executor(node_def)
        # -------------------------

        # Récupération des items entrants (provenant des nœuds parents)
        # Pour le MVP, on simplifie : on prend les outputs des nœuds connectés
        input_items = self._resolve_inputs(node_id, context, wf_def)

        # Enregistrement du début de step
        start_time = datetime.datetime.now()

        try:
            # Appel de l'exécuteur concret
            output_items = executor.execute(
                node_def=node_def,
                input_items=input_items,
                context=context,
                security_provider=self.security_provider,
                http_helper=self.http_helper
            )

            # Log de télémétrie dans le contexte
            execution_time = (datetime.datetime.now() - start_time).total_seconds() * 1000
            context.record_step(
                node_id=node_id,
                node_type=node_def.type,
                status="success",
                input_count=len(input_items),
                output_count=len(output_items),
                execution_time_ms=int(execution_time)
            )

            return output_items

        except engine_errors.N8nLifeEngineError as e:
            # On enrichit l'erreur avec l'ID du nœud fautif
            e.details = getattr(e, 'details', {})
            e.details['node_id'] = node_id
            
            context.record_step(
                node_id=node_id,
                node_type=node_def.type,
                status="failed",
                error_code=e.error_code,
                error_message=str(e)
            )
            raise e

    def _resolve_inputs(self, node_id: str, context: engine_context.WorkflowContext, wf_def: nodes_base.WorkflowDefinition) -> List[engine_context.Item]:
        """
        Collecte les items produits par les nœuds parents.
        """
        # Dans un DAG, on cherche qui pointe vers node_id
        inputs = []
        for source_id, conns in wf_def.connections.items():
            for c in conns:
                if c.get('target_id') == node_id:
                    parent_outputs = context.node_outputs.get(source_id, [])
                    inputs.extend(parent_outputs)
        
        # Si c'est le trigger ou un nœud orphelin, on peut avoir des données dans trigger_items
        if not inputs and node_id in wf_def.nodes:
            if node_id == context.step_history[0]['node_id'] if context.step_history else None:
                return getattr(context, 'trigger_items', [])
                
        return inputs