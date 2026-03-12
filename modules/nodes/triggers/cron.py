# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/nodes/triggers/cron.py

import importlib
from typing import List

import applications.reasoningframe.modules.nodes.base as nodes_base
import applications.reasoningframe.modules.engine.context as engine_context
import applications.reasoningframe.modules.engine.errors as engine_errors

importlib.reload(nodes_base)
importlib.reload(engine_context)
importlib.reload(engine_errors)

class CronTriggerNode(nodes_base.NodeExecutor):
    """
    Représente le point d'entrée d'un workflow déclenché par une horloge externe.
    Namespace : reasoningframe
    """

    def execute(
        self,
        node_def: nodes_base.NodeDefinition,
        input_items: List[engine_context.Item],
        context: engine_context.WorkflowContext,
        security_provider=None,
        http_helper=None
    ) -> List[engine_context.Item]:

        if node_def.type != "trigger.cron":
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message=f"Le CronTriggerNode ne peut pas exécuter un node de type '{node_def.type}'.",
                error_code="ERR_INVALID_TRIGGER_TYPE"
            )

        # Résolution du payload (input_items > trigger_items > current_items)
        source_items = input_items or getattr(context, "trigger_items", []) or context.current_items

        if not source_items:
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Déclencheur cron vide : aucun signal temporel injecté.",
                error_code="ERR_TRIGGER_NO_PAYLOAD"
            )

        for i, item in enumerate(source_items):
            if not isinstance(item, engine_context.Item):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Élément {i} invalide : type Item attendu.",
                    error_code="ERR_INVALID_ITEM_TYPE"
                )

            payload = item.json or {}
            if not isinstance(payload, dict) or not payload.get("triggered_at"):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Payload cron invalide à l'index {i} : 'triggered_at' requis.",
                    error_code="ERR_CRON_MISSING_TRIGGERED_AT"
                )

        return source_items