# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/security/expressions.py

import re
import importlib
from typing import Any, Optional

# Imports avec reload pour le dev web2py
import applications.reasoningframe.modules.engine.errors as engine_errors
importlib.reload(engine_errors)

import applications.reasoningframe.modules.engine.context as engine_context
importlib.reload(engine_context)

class ExpressionParser:
    """
    Parser sandboxé et déterministe pour résoudre les expressions dynamiques.
    Ne fait AUCUNE évaluation Python native (pas de eval/exec).
    """
    
    # Regex stricte : on capture ce qui est entre {{ et }}
    TAG_PATTERN = re.compile(r"\{\{\s*(.*?)\s*\}\}")

    @staticmethod
    def resolve(value: Any, 
                context: engine_context.WorkflowContext, 
                current_item: Optional[engine_context.Item] = None) -> Any:
        """Point d'entrée récursif."""
        if isinstance(value, str):
            return ExpressionParser._resolve_string(value, context, current_item)
        elif isinstance(value, dict):
            return {k: ExpressionParser.resolve(v, context, current_item) for k, v in value.items()}
        elif isinstance(value, list):
            return [ExpressionParser.resolve(item, context, current_item) for item in value]
        return value

    @staticmethod
    def _resolve_string(text: str, 
                        context: engine_context.WorkflowContext, 
                        current_item: Optional[engine_context.Item]) -> Any:
        
        matches = list(ExpressionParser.TAG_PATTERN.finditer(text))
        
        if not matches:
            return text
            
        # RÈGLE MVP : Préservation du type natif si la string n'est qu'un seul tag exact
        if len(matches) == 1 and matches[0].group(0) == text.strip():
            path = matches[0].group(1)
            return ExpressionParser._get_value_from_path(path, context, current_item)

        # Interpolation pour les strings mixtes (ex: "ID: {{ current.json.id }}")
        result_text = text
        for match in matches:
            full_tag = match.group(0)
            path = match.group(1)
            
            val = ExpressionParser._get_value_from_path(path, context, current_item)
            result_text = result_text.replace(full_tag, str(val))
            
        return result_text

    @staticmethod
    def _get_value_from_path(path: str, 
                             context: engine_context.WorkflowContext, 
                             current_item: Optional[engine_context.Item]) -> Any:
        
        parts = path.split('.')
        root = parts[0]

        try:
            # ---------------------------------------------------------
            # BRANCHE A : Accès à l'historique (steps.*)
            # ---------------------------------------------------------
            if root == 'steps':
                if len(parts) < 3:
                    raise engine_errors.ExpressionEvaluationError(path, "Incomplete path (expected: steps.<node_id>.<prop>)")
                
                node_id = parts[1]
                
                # Repose sur la levée de NodeOutputNotFoundError par le contexte
                try:
                    node_output = context.get_node_output(node_id)
                except engine_errors.NodeOutputNotFoundError as e:
                    raise engine_errors.ExpressionEvaluationError(path, str(e))
                
                if not node_output:
                    raise engine_errors.ExpressionEvaluationError(path, f"No output data for node '{node_id}'")
                
                current_obj = node_output[0]
                remaining_path = parts[2:]

            # ---------------------------------------------------------
            # BRANCHE B : Accès à l'item courant (current.*)
            # ---------------------------------------------------------
            elif root == 'current':
                if current_item is None:
                    raise engine_errors.ExpressionEvaluationError(path, "'current' context unavailable")
                
                current_obj = current_item
                remaining_path = parts[1:]

            else:
                raise engine_errors.ExpressionEvaluationError(path, f"Invalid root '{root}' (allowed: steps, current)")

            # ---------------------------------------------------------
            # NAVIGATION STRICTE (Fail-Fast)
            # ---------------------------------------------------------
            for part in remaining_path:
                if isinstance(current_obj, dict):
                    if part not in current_obj:
                        raise engine_errors.ExpressionEvaluationError(path, f"Key '{part}' not found in dict")
                    current_obj = current_obj[part]
                else:
                    if not hasattr(current_obj, part):
                        raise engine_errors.ExpressionEvaluationError(path, f"Attribute '{part}' not found on object")
                    current_obj = getattr(current_obj, part)

            return current_obj

        except engine_errors.N8nLifeEngineError:
            raise
        except Exception as e:
            raise engine_errors.ExpressionEvaluationError(path, f"Unexpected error: {str(e)}")