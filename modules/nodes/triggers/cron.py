# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/nodes/triggers/cron.py

import importlib
from typing import List

import applications.reasoningframe.modules.nodes.base as nodes_base
import applications.reasoningframe.modules.engine.context as engine_context
import applications.reasoningframe.modules.engine.errors as engine_errors # Note: à changer en reasoningframe si le module error a bougé

importlib.reload(nodes_base)
importlib.reload(engine_context)
importlib.reload(engine_errors)

class CronTriggerNode(nodes_base.NodeExecutor):
    """
    Représente le point d'entrée d'un workflow déclenché par une horloge.
    
    RÔLE RUNTIME :
    Valide et transmet le signal temporel injecté par le scheduler externe.
    """

    def execute(
        self,
        node_def: nodes_base.NodeDefinition,
        input_items: List[engine_context.Item],
        context: engine_context.WorkflowContext,
        security_provider=None,
        http_helper=None
    ) -> List[engine_context.Item]:

        # 1. Validation de l'identité du node
        if node_def.type != "trigger.cron":
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message=f"Le CronTriggerNode ne peut pas exécuter un node de type '{node_def.type}'.",
                error_code="ERR_INVALID_TRIGGER_TYPE"
            )

        # 2. Résolution du payload (Alignement strict avec WorkflowContext)
        # On utilise input_items (priorité Runner) ou current_items (vérité du contexte)
        source_items = input_items or getattr(context, "current_items", [])

        # 3. Fail-fast si aucun signal cron n'est disponible
        if not source_items:
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Déclencheur cron vide : aucun signal temporel n'a été injecté au démarrage.",
                error_code="ERR_TRIGGER_NO_PAYLOAD"
            )

        # 4. Validation stricte du contrat Item et du Payload
        for i, item in enumerate(source_items):
            if not isinstance(item, engine_context.Item):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Élément d'index {i} invalide : type Item attendu.",
                    error_code="ERR_INVALID_ITEM_TYPE"
                )

            payload = item.json or {}
            if not isinstance(payload, dict):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Payload cron invalide : dictionnaire attendu.",
                    error_code="ERR_INVALID_TRIGGER_PAYLOAD"
                )

            # Vérification du champ obligatoire 'triggered_at'
            if not payload.get("triggered_at"):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Payload cron invalide : champ 'triggered_at' requis.",
                    error_code="ERR_CRON_MISSING_TRIGGERED_AT"
                )

            # Vérification de la source pour éviter les collisions de déclencheurs
            source = payload.get("source")
            if source and source != "cron":
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Source incohérente pour un trigger cron : '{source}'.",
                    error_code="ERR_CRON_INVALID_SOURCE"
                )

        # 5. Transmission
        return source_items