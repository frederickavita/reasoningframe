# -*- coding: utf-8 -*-
# applications/n8n_life/modules/nodes/triggers/webhook.py

import importlib
from typing import List

import applications.reasoningframe.modules.nodes.base as nodes_base
import applications.reasoningframe.modules.engine.context as engine_context
import applications.reasoningframe.modules.engine.errors as engine_errors

importlib.reload(nodes_base)
importlib.reload(engine_context)
importlib.reload(engine_errors)

class WebhookTriggerNode(nodes_base.NodeExecutor):
    """
    Représente le point d'entrée d'un workflow déclenché par un Webhook.
    
    RÔLE RUNTIME :
    Ce node ne traite pas l'HTTP. Il agit comme un validateur de contrat 
    entre le WebhookService (amont) et le reste du DAG (aval).
    """

    def execute(self, 
                node_def: nodes_base.NodeDefinition, 
                input_items: List[engine_context.Item], 
                context: engine_context.WorkflowContext, 
                security_provider=None, 
                http_helper=None) -> List[engine_context.Item]:
        
        # 1. Validation de l'identité du node
        if not node_def.type.startswith("trigger."):
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message=f"Type invalide pour un exécuteur de trigger : {node_def.type}",
                error_code="ERR_INVALID_TRIGGER_TYPE"
            )

        # 2. Résolution du payload avec priorité sémantique :
        # A. input_items : Fourni explicitement par le Runner (cas standard)
        # B. context.trigger_items : La source de vérité immuable du démarrage
        # C. context.current_items : Fallback de dernier recours (cache courant)
        
        source_items = input_items
        
        if not source_items and hasattr(context, 'trigger_items'):
            source_items = context.trigger_items
            
        if not source_items:
            source_items = context.current_items

        # 3. Fail-Fast si aucune donnée n'est disponible
        if not source_items:
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Déclencheur Webhook vide : aucun payload n'a été injecté au démarrage.",
                error_code="ERR_TRIGGER_NO_PAYLOAD"
            )

        # 4. Validation du type Item (Contrat strict du moteur)
        for i, item in enumerate(source_items):
            if not isinstance(item, engine_context.Item):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Élément d'index {i} invalide : type Item attendu.",
                    error_code="ERR_INVALID_ITEM_TYPE"
                )

        # 5. Transmission au reste du graphe
        # Le payload est déjà normalisé par le WebhookService.
        return source_items