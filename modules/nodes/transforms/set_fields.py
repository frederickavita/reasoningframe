# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/nodes/transforms/set_fields.py

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


class SetFieldsNode(nodes_base.NodeExecutor):
    """
    Transform node minimal :
    - ajoute des champs
    - renomme des clés top-level
    - construit un JSON simple
    - résout les expressions autorisées

    Ne fait PAS :
    - réseau
    - secrets
    - DAL
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
        if node_def.type != "transform.set_fields":
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message=f"Le SetFieldsNode ne peut pas exécuter un node de type '{node_def.type}'.",
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

        mode = raw_params.get("mode", "merge")
        fields_template = raw_params.get("fields", {})
        rename_map = raw_params.get("rename", {})

        if mode not in ("merge", "replace"):
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Le paramètre 'mode' doit valoir 'merge' ou 'replace'.",
                error_code="ERR_INVALID_SET_FIELDS_MODE"
            )

        if not isinstance(fields_template, dict):
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Le paramètre 'fields' doit être un dictionnaire.",
                error_code="ERR_INVALID_SET_FIELDS_FIELDS"
            )

        if not isinstance(rename_map, dict):
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Le paramètre 'rename' doit être un dictionnaire.",
                error_code="ERR_INVALID_SET_FIELDS_RENAME"
            )

        # Recommandation MVP stricte : pas de rename en mode replace
        if mode == "replace" and rename_map:
            raise engine_errors.NodeExecutionError(
                node_id=node_def.id,
                message="Le paramètre 'rename' n'est pas autorisé en mode 'replace'.",
                error_code="ERR_SET_FIELDS_RENAME_NOT_ALLOWED"
            )

        # ==============================================================
        # 3. Transform, pas trigger : s'il n'a pas d'input, il ne crée rien
        # ==============================================================
        if not input_items:
            return []

        output_items = []

        # ==============================================================
        # 4. Traitement item par item
        # ==============================================================
        for i, item in enumerate(input_items):

            if not isinstance(item, engine_context.Item):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Élément d'entrée invalide à l'index {i} : type Item attendu.",
                    error_code="ERR_INVALID_ITEM_TYPE"
                )

            if not isinstance(item.json, dict):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Le json de l'item d'entrée {i} doit être un dictionnaire.",
                    error_code="ERR_INVALID_ITEM_JSON"
                )

            # ----------------------------------------------------------
            # 4.a Base JSON selon le mode
            # ----------------------------------------------------------
            if mode == "merge":
                new_json = dict(item.json)   # copie top-level simple MVP
            else:
                new_json = {}

            # ----------------------------------------------------------
            # 4.b Renommage top-level strict (mode merge uniquement)
            # ----------------------------------------------------------
            if rename_map:
                for old_key, new_key in rename_map.items():

                    if not isinstance(old_key, str) or not old_key:
                        raise engine_errors.NodeExecutionError(
                            node_id=node_def.id,
                            message="Les clés de 'rename' doivent être des strings non vides.",
                            error_code="ERR_INVALID_RENAME_SOURCE_KEY"
                        )

                    if not isinstance(new_key, str) or not new_key:
                        raise engine_errors.NodeExecutionError(
                            node_id=node_def.id,
                            message="Les valeurs de 'rename' doivent être des strings non vides.",
                            error_code="ERR_INVALID_RENAME_TARGET_KEY"
                        )

                    if old_key not in new_json:
                        raise engine_errors.NodeExecutionError(
                            node_id=node_def.id,
                            message=f"Impossible de renommer '{old_key}' : clé absente.",
                            error_code="ERR_RENAME_SOURCE_MISSING"
                        )

                    value = new_json.pop(old_key)
                    new_json[new_key] = value

            # ----------------------------------------------------------
            # 4.c Résolution dynamique des champs à poser
            # ----------------------------------------------------------
            try:
                resolved_fields = sec_expr.ExpressionParser.resolve(
                    value=fields_template,
                    context=context,
                    current_item=item
                )
            except engine_errors.ExpressionEvaluationError as e:
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Erreur d'évaluation des champs: {str(e)}",
                    error_code="ERR_SET_FIELDS_EXPRESSION"
                )

            if not isinstance(resolved_fields, dict):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message="Après résolution, 'fields' doit rester un dictionnaire.",
                    error_code="ERR_INVALID_RESOLVED_FIELDS"
                )

            # ----------------------------------------------------------
            # 4.d Application finale des champs (MVP = top-level seulement)
            # ----------------------------------------------------------
            for field_name, field_value in resolved_fields.items():
                if not isinstance(field_name, str) or not field_name:
                    raise engine_errors.NodeExecutionError(
                        node_id=node_def.id,
                        message="Chaque nom de champ produit doit être une string non vide.",
                        error_code="ERR_INVALID_OUTPUT_FIELD_NAME"
                    )

                new_json[field_name] = field_value

            # ----------------------------------------------------------
            # 4.e Préservation de la traçabilité
            # ----------------------------------------------------------
            new_item = engine_context.Item(
                json=new_json,
                paired_item=item.paired_item,
                binary=item.binary
            )
            new_item.meta = dict(item.meta or {})
            output_items.append(new_item)

        # ==============================================================
        # 5. Retour strict du contrat moteur
        # ==============================================================
        return output_items