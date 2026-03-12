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
    Note : La sécurité (HMAC) et le parsing sont gérés en amont par le WebhookService.
    Ce node valide simplement que le payload est disponible pour la suite du graphe.
    """

    def execute(self, 
                node_def: nodes_base.NodeDefinition, 
                input_items: List[engine_context.Item], 
                context: engine_context.WorkflowContext, 
                security_provider=None, 
                http_helper=None) -> List[engine_context.Item]:
        
        # 1. Vérification du type de node
        if node_def.type != "trigger.webhook":
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message=f"Le WebhookTriggerNode ne peut pas exécuter un node de type '{node_def.type}'.",
                error_code="ERR_INVALID_TRIGGER_TYPE"
            )

        # 2. Résolution du payload (Priorité : input_items > context.current_items)
        # Dans le flux standard, le Runner injecte le payload dans input_items au démarrage.
        source_items = input_items if input_items else context.current_items

        if not source_items:
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Aucun payload webhook exploitable trouvé (le point d'entrée est vide).",
                error_code="ERR_TRIGGER_NO_PAYLOAD"
            )

        # 3. Validation du contrat Item
        for item in source_items:
            if not isinstance(item, engine_context.Item):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message="Données d'entrée corrompues : les éléments doivent être de type Item.",
                    error_code="ERR_INVALID_ITEM_TYPE"
                )

        # 4. Retourne les items tels quels pour le prochain node
        # Le payload normalisé par le WebhookService est déjà prêt à l'emploi.
        return source_items