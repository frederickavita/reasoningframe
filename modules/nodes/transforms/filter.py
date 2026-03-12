# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/nodes/transforms/filter.py

import importlib
from typing import List, Any

import applications.reasoningframe.modules.nodes.base as nodes_base
import applications.reasoningframe.modules.engine.context as engine_context
import applications.reasoningframe.modules.security.expressions as sec_expr
import applications.reasoningframe.modules.engine.errors as engine_errors

importlib.reload(nodes_base)
importlib.reload(engine_context)
importlib.reload(sec_expr)
importlib.reload(engine_errors)


class FilterNode(nodes_base.NodeExecutor):
    """
    Transform node minimal :
    - conserve certains items
    - rejette certains items
    - repose sur une condition déterministe
    - utilise uniquement les expressions autorisées

    Ne fait PAS :
    - réseau
    - DAL
    - crypto
    - comportement de trigger
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
        if node_def.type != "transform.filter":
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message=f"Le FilterNode ne peut pas exécuter un node de type '{node_def.type}'.",
                error_code="ERR_INVALID_TRANSFORM_TYPE"
            )

        # ==============================================================
        # 2. Extraction / validation des paramètres statiques
        # ==============================================================
        raw_params = node_def.parameters or {}

        if not isinstance(raw_params, dict):
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Les paramètres du node doivent être un dictionnaire.",
                error_code="ERR_INVALID_NODE_PARAMETERS"
            )

        if "condition" not in raw_params:
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Le paramètre 'condition' est obligatoire.",
                error_code="ERR_FILTER_CONDITION_MISSING"
            )

        condition_template = raw_params.get("condition")
        mode = raw_params.get("mode", "keep_if_true")
        strict_bool = raw_params.get("strict_bool", False)

        if mode not in ("keep_if_true", "drop_if_true"):
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Le paramètre 'mode' doit valoir 'keep_if_true' ou 'drop_if_true'.",
                error_code="ERR_INVALID_FILTER_MODE"
            )

        if not isinstance(strict_bool, bool):
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Le paramètre 'strict_bool' doit être un booléen.",
                error_code="ERR_INVALID_FILTER_STRICT_BOOL"
            )

        # ==============================================================
        # 3. Transform, pas trigger : s'il n'a pas d'input, il ne crée rien
        # ==============================================================
        if not input_items:
            return []

        output_items = []

        # ==============================================================
        # 4. Évaluation item par item
        # ==============================================================
        for i, item in enumerate(input_items):

            if not isinstance(item, engine_context.Item):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Élément d'entrée invalide à l'index {i} : type Item attendu.",
                    error_code="ERR_INVALID_ITEM_TYPE"
                )

            try:
                # Résolution dynamique sécurisée (fail-fast, sans eval)
                resolved_condition = sec_expr.ExpressionParser.resolve(
                    value=condition_template,
                    context=context,
                    current_item=item
                )
            except engine_errors.ExpressionEvaluationError as e:
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Erreur d'évaluation de la condition: {str(e)}",
                    error_code="ERR_FILTER_EXPRESSION"
                )

            # ----------------------------------------------------------
            # 4.a Interprétation stricte ou permissive
            # ----------------------------------------------------------
            if strict_bool:
                if not isinstance(resolved_condition, bool):
                    raise engine_errors.NodeExecutionError(
                        node_id=node_def.id,
                        message=(
                            f"La condition résolue pour l'item {i} doit être un booléen "
                            f"quand strict_bool=True."
                        ),
                        error_code="ERR_FILTER_NOT_BOOL",
                        details={"item_index": i, "resolved_type": type(resolved_condition).__name__}
                    )
                keep_item = resolved_condition
            else:
                keep_item = bool(resolved_condition)

            # ----------------------------------------------------------
            # 4.b Application du mode
            # ----------------------------------------------------------
            if mode == "drop_if_true":
                keep_item = not keep_item

            # ----------------------------------------------------------
            # 4.c Conservation de l'item
            # ----------------------------------------------------------
            if keep_item:
                # On ajoute la référence de l'item tel quel (traçabilité préservée)
                output_items.append(item)

        # ==============================================================
        # 5. Retour strict du contrat moteur
        # ==============================================================
        return output_items