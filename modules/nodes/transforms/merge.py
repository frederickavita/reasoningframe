# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/nodes/transforms/merge.py

import importlib
import json
from typing import List, Any

import applications.reasoningframe.modules.nodes.base as nodes_base
import applications.reasoningframe.modules.engine.context as engine_context
import applications.reasoningframe.modules.engine.errors as engine_errors

importlib.reload(nodes_base)
importlib.reload(engine_context)
importlib.reload(engine_errors)


class MergeNode(nodes_base.NodeExecutor):
    """
    Transform node MVP de recomposition.

    Ce node NE FAIT PAS un vrai join inter-branches intelligent.
    Avec le runner actuel, il reçoit déjà une liste plate de Item.

    Rôle MVP :
    - concaténer / relayer les items entrants
    - dédupliquer si demandé
    - garder le premier / dernier si demandé
    - rester déterministe et fail-fast
    """

    def execute(
        self,
        node_def: nodes_base.NodeDefinition,
        input_items: List[engine_context.Item],
        context: engine_context.WorkflowContext,
        security_provider: Any,
        http_helper: Any
    ) -> List[engine_context.Item]:

        # ==============================================================
        # 1. Validation stricte de l'identité du node
        # ==============================================================
        if node_def.type != "transform.merge":
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message=f"Le MergeNode ne peut pas exécuter un node de type '{node_def.type}'.",
                error_code="ERR_INVALID_TRANSFORM_TYPE"
            )

        # ==============================================================
        # 2. Validation des paramètres
        # ==============================================================
        raw_params = node_def.parameters or {}

        if not isinstance(raw_params, dict):
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Les paramètres du node doivent être un dictionnaire.",
                error_code="ERR_INVALID_NODE_PARAMETERS"
            )

        mode = raw_params.get("mode", "append")

        allowed_modes = {
            "append",        # relaye tous les items dans l'ordre
            "dedupe_json",   # retire les doublons exacts sur item.json
            "first_only",    # garde seulement le premier
            "last_only"      # garde seulement le dernier
        }

        if mode not in allowed_modes:
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message=(
                    "Le paramètre 'mode' doit valoir "
                    "'append', 'dedupe_json', 'first_only' ou 'last_only'."
                ),
                error_code="ERR_INVALID_MERGE_MODE"
            )

        # ==============================================================
        # 3. Transform pur : pas d'input => pas de création artificielle
        # ==============================================================
        if not input_items:
            return []

        # ==============================================================
        # 4. Validation stricte du contrat Item
        # ==============================================================
        for i, item in enumerate(input_items):
            if not isinstance(item, engine_context.Item):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Élément d'entrée invalide à l'index {i} : type Item attendu.",
                    error_code="ERR_INVALID_ITEM_TYPE"
                )
            
            # --- AMÉLIORATION APPLIQUÉE ICI ---
            # Validation explicite que le payload JSON est bien un dictionnaire
            # avant de tenter de le cloner ou de le sérialiser.
            if not isinstance(item.json, dict):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Le json de l'item d'entrée {i} doit être un dictionnaire.",
                    error_code="ERR_INVALID_ITEM_JSON"
                )

        # ==============================================================
        # 5. Clonage propre des items entrants
        #    On reconstruit la traçabilité explicitement pour les outputs.
        # ==============================================================
        prepared_items = []
        for index, item in enumerate(input_items):
            new_item = engine_context.Item(
                json=dict(item.json),     # Désormais sécurisé par la validation (4)
                binary=dict(item.binary) if item.binary else {},
                paired_item={"source_node_id": node_def.id, "source_index": index}
            )
            new_item.meta = dict(item.meta) if item.meta else {}
            prepared_items.append(new_item)

        # ==============================================================
        # 6. Application du mode
        # ==============================================================
        if mode == "append":
            return prepared_items

        if mode == "first_only":
            return [prepared_items[0]]

        if mode == "last_only":
            return [prepared_items[-1]]

        if mode == "dedupe_json":
            deduped = []
            seen = set()

            for item in prepared_items:
                try:
                    # déterministe : sérialisation triée
                    signature = json.dumps(item.json, sort_keys=True, ensure_ascii=False)
                except Exception as e:
                    raise engine_errors.NodeExecutionError(
                        node_id=node_def.id,
                        message=f"Impossible de sérialiser item.json pour déduplication : {str(e)}",
                        error_code="ERR_MERGE_DEDUPE_SERIALIZATION"
                    )

                if signature not in seen:
                    seen.add(signature)
                    deduped.append(item)

            return deduped

        # ==============================================================
        # 7. Sécurité finale
        # ==============================================================
        raise engine_errors.NodeExecutionError(
            node_id=node_def.id,
            message="Mode de merge non traité malgré validation préalable.",
            error_code="ERR_MERGE_UNREACHABLE_STATE"
        )