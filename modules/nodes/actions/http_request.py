# -*- coding: utf-8 -*-
# applications/n8n_life/modules/nodes/actions/http_request.py

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

class HttpRequestNode(nodes_base.NodeExecutor):
    """
    Nœud HTTP Request : Le couteau suisse pour appeler des API externes.
    """

    def execute(self, 
                node_def: nodes_base.NodeDefinition, 
                input_items: List[engine_context.Item], 
                context: engine_context.WorkflowContext, 
                security_provider: Any, 
                http_helper: Any) -> List[engine_context.Item]:
        
        output_items = []

        # Règle Moteur : Si pas d'inputs, on crée un Item factice vide
        items_to_process = input_items if input_items else [engine_context.Item(json={})]

        for item in items_to_process:
            # 1. Résolution dynamique des paramètres
            try:
                resolved_params = sec_expr.ExpressionParser.resolve(
                    value=node_def.parameters, 
                    context=context, 
                    current_item=item
                )
            except engine_errors.ExpressionEvaluationError as e:
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Erreur d'évaluation des paramètres: {str(e)}"
                )

            # 1.bis Vérification critique (Fail-Fast) : Les paramètres résolus DOIVENT être un dictionnaire
            if not isinstance(resolved_params, dict):
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message="Les paramètres du nœud doivent former un dictionnaire valide après résolution."
                )

            # 2. Extraction et Validation stricte des types
            url = resolved_params.get("url")
            if not isinstance(url, str) or not url.strip():
                raise engine_errors.NodeExecutionError(node_def.id, "Le paramètre 'url' est obligatoire et doit être une string.")

            method = resolved_params.get("method", "GET")
            if not isinstance(method, str):
                raise engine_errors.NodeExecutionError(node_def.id, "Le paramètre 'method' doit être une string.")

            headers_param = resolved_params.get("headers", {})
            if not isinstance(headers_param, dict):
                raise engine_errors.NodeExecutionError(node_def.id, "Le paramètre 'headers' doit être un dictionnaire.")

            query_params = resolved_params.get("query_parameters", {})
            if not isinstance(query_params, dict):
                raise engine_errors.NodeExecutionError(node_def.id, "Le paramètre 'query_parameters' doit être un dictionnaire.")

            json_body = resolved_params.get("json_body")
            data_body = resolved_params.get("data_body") # Ajout pour formulaires/fichiers
            
            raw_timeout = resolved_params.get("timeout", 20)
            try:
                timeout = float(raw_timeout)
                if timeout <= 0:
                    raise ValueError()
            except (ValueError, TypeError):
                raise engine_errors.NodeExecutionError(node_def.id, f"Valeur de 'timeout' invalide : {raw_timeout}")

            # 3. Injection des Secrets via le Security Provider
            final_headers = {}
            if node_def.credential_key and security_provider:
                secret_dict = security_provider.get_decrypted_secret(node_def.credential_key)
                if isinstance(secret_dict, dict):
                    final_headers.update(secret_dict)
                else:
                    raise engine_errors.NodeExecutionError(
                        node_def.id, 
                        "Format de secret invalide. Pour le nœud HTTP, le secret doit être un dictionnaire."
                    )
            
            # Priorité locale : les headers explicites du nœud écrasent ceux du Vault
            final_headers.update(headers_param)

            # 4. Appel Réseau via la façade
            try:
                response_data = http_helper.send_request(
                    method=method,
                    url=url,
                    headers=final_headers,
                    query_params=query_params,
                    json_body=json_body,
                    data_body=data_body,
                    timeout=timeout
                )
            except engine_errors.NodeExecutionError as e:
                safe_details = getattr(e, 'details', {})
                raise engine_errors.NodeExecutionError(
                    node_id=node_def.id,
                    message=f"Échec de la requête HTTP: {str(e)}",
                    details=safe_details
                )

            # 5. Normalisation du Body pour le contrat Item(json=Dict)
            raw_body = response_data.get("body")
            if isinstance(raw_body, dict):
                out_json = raw_body
            elif raw_body is None:
                out_json = {}
            else:
                out_json = {"data": raw_body}

            # 6. Enrichissement des métadonnées
            out_meta = {
                "http_status_code": response_data.get("status_code"),
                "http_headers": response_data.get("headers"),
                "request_preview": response_data.get("request_preview", {})
            }

            # Création propre
            new_item = engine_context.Item(json=out_json, binary=None)
            new_item.meta = out_meta
            output_items.append(new_item)

        return output_items