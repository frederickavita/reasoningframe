# -*- coding: utf-8 -*-
# applications/n8n_life/modules/nodes/registry.py

import importlib
from typing import Dict, Any, Type, Union

import applications.reasoningframe.modules.nodes.base as nodes_base
import applications.reasoningframe.modules.engine.errors as engine_errors

importlib.reload(nodes_base)
importlib.reload(engine_errors)

class NodeRegistry:
    """
    Annuaire central des exécuteurs de nœuds.
    Fait le pont entre un type (ex: 'trigger.webhook') et sa classe Python.
    """
    
    # Stockage statique des classes d'exécution
    _executors: Dict[str, Type[nodes_base.NodeExecutor]] = {}

    @classmethod
    def register(cls, node_type: str, executor_class: Type[nodes_base.NodeExecutor]):
        """Enregistre un nouveau type de nœud dans le catalogue."""
        cls._executors[node_type] = executor_class

    @classmethod
    def get_executor(cls, node_input: Union[str, nodes_base.NodeDefinition]) -> nodes_base.NodeExecutor:
        """
        Récupère une instance d'exécuteur.
        Supporte l'objet NodeDefinition (utilisé par le Runner) ou une string (pour tests).
        """
        # Résolution du type
        if isinstance(node_input, str):
            node_type = node_input
        elif hasattr(node_input, 'type'):
            node_type = node_input.type
        else:
            raise engine_errors.N8nLifeEngineError(
                "Le Registry a reçu un format de nœud inconnu.", 
                "ERR_REGISTRY_INVALID_INPUT"
            )

        # Recherche de la classe
        executor_class = cls._executors.get(node_type)
        
        if not executor_class:
            raise engine_errors.N8nLifeEngineError(
                message=f"Le type de nœud '{node_type}' n'est pas enregistré dans le catalogue.",
                error_code="ERR_NODE_TYPE_UNKNOWN",
                details={"node_type": node_type}
            )

        # Retourne une instance fraîche pour l'exécution
        return executor_class()

    @classmethod
    def clear(cls):
        """Vide le catalogue (utile pour le hot-reload de web2py)."""
        cls._executors = {}