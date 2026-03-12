# -*- coding: utf-8 -*-
# applications/n8n_life/modules/engine/errors.py

class WebhookValidationError(N8nLifeEngineError):
    """Levée quand une signature de webhook entrante est absente ou invalide."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, error_code="ERR_WEBHOOK_VALIDATION", details=details)


class N8nLifeEngineError(Exception):
    """Classe racine. Gère le message, le code d'erreur et les détails structurés."""
    def __init__(self, message: str, error_code: str = "ERR_ENGINE_GENERIC", details: dict = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}

class GraphValidationError(N8nLifeEngineError):
    """Erreur de parsing ou de cohérence structurelle du graphe."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, error_code="ERR_GRAPH_INVALID", details=details)

class NodeExecutionError(N8nLifeEngineError):
    """Erreur lors de l'exécution d'un nœud spécifique."""
    def __init__(self, node_id: str, message: str, error_code: str = "ERR_NODE_EXECUTION", details: dict = None):
        self.node_id = node_id
        # On enrichit les détails avec l'ID du nœud fautif
        full_details = {"node_id": node_id}
        if details: full_details.update(details)
        super().__init__(f"Node '{node_id}' failed: {message}", error_code=error_code, details=full_details)

class NodeOutputNotFoundError(N8nLifeEngineError):
    """Levée quand on tente d'accéder à l'output d'un nœud qui n'a pas tourné."""
    def __init__(self, node_id: str):
        self.node_id = node_id
        super().__init__(
            f"Output for node '{node_id}' not found.", 
            error_code="ERR_NODE_OUTPUT_MISSING",
            details={"node_id": node_id}
        )

class MissingCredentialError(N8nLifeEngineError):
    """Levée quand une référence de secret ne peut pas être résolue."""
    def __init__(self, credential_key: str):
        self.credential_key = credential_key
        super().__init__(
            f"Credential '{credential_key}' missing.", 
            error_code="ERR_CREDENTIAL_MISSING",
            details={"credential_key": credential_key}
        )

class ExpressionEvaluationError(N8nLifeEngineError):
    """Levée quand la résolution d'une variable dynamique échoue dans la sandbox."""
    def __init__(self, expression: str, message: str):
        self.expression = expression
        super().__init__(
            f"Expression evaluation failed: {expression} -> {message}", 
            error_code="ERR_EXPRESSION_EVAL",
            details={"expression": expression}
        )