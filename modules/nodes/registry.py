# -*- coding: utf-8 -*-
# applications/n8n_life/modules/nodes/registry.py

import importlib
from typing import Dict, Any, Type, Union

import applications.reasoningframe.modules.nodes.base as nodes_base
import applications.reasoningframe.modules.engine.errors as engine_errors

class NodeRegistry:
    _executors: Dict[str, Type[nodes_base.NodeExecutor]] = {}

    @classmethod
    def register(cls, node_type: str, executor_class: Type[nodes_base.NodeExecutor]):
        cls._executors[node_type] = executor_class

    @classmethod
    def get_executor(cls, node_input: Union[str, nodes_base.NodeDefinition]) -> nodes_base.NodeExecutor:
        """
        RÉSOUD LE MISMATCH : Accepte indifféremment le type (str) ou l'objet (NodeDefinition).
        """
        # Résolution du type de nœud
        if isinstance(node_input, str):
            node_type = node_input
        elif hasattr(node_input, 'type'):
            node_type = node_input.type
        else:
            raise engine_errors.N8nLifeEngineError(
                "Entrée invalide pour le Registry (str ou NodeDefinition attendu).",
                "ERR_REGISTRY_INVALID_INPUT"
            )

        executor_class = cls._executors.get(node_type)
        if not executor_class:
            raise engine_errors.N8nLifeEngineError(
                f"Type de nœud inconnu : {node_type}",
                "ERR_NODE_TYPE_UNKNOWN"
            )

        return executor_class()

    @classmethod
    def clear(cls):
        cls._executors = {}