# -*- coding: utf-8 -*-
# applications/n8n_life/modules/nodes/registry.py

import importlib
from typing import Type, Dict

import applications.reasoningframe.modules.nodes.base as nodes_base
import applications.reasoningframe.modules.engine.errors as engine_errors

importlib.reload(nodes_base)
importlib.reload(engine_errors)

class NodeRegistry:
    """
    L'Annuaire Central.
    Associe un identifiant de type (ex: 'core.set') à sa classe d'exécution.
    """
    _executors: Dict[str, Type[nodes_base.NodeExecutor]] = {}

    @classmethod
    def register(cls, node_type: str, executor_class: Type[nodes_base.NodeExecutor]):
        """
        Enregistre un nouveau type de nœud dans le système.
        Note d'architecture : L'écrasement silencieux d'un nœud existant est autorisé 
        et assumé ici pour supporter le hot-reloading (importlib.reload) propre à web2py.
        """
        if not issubclass(executor_class, nodes_base.NodeExecutor):
            raise ValueError(f"La classe {executor_class.__name__} doit hériter de NodeExecutor.")
            
        cls._executors[node_type] = executor_class

    @classmethod
    def get_executor(cls, node_type: str) -> nodes_base.NodeExecutor:
        """
        Instancie et retourne l'exécuteur demandé. (Fail-Fast si inconnu).
        """
        if node_type not in cls._executors:
            raise engine_errors.N8nLifeEngineError(
                f"Le type de nœud '{node_type}' n'est pas reconnu par le moteur.",
                error_code="ERR_NODE_TYPE_UNKNOWN",
                details={"requested_type": node_type}
            )
        
        # On retourne une instance neuve (Stateless)
        executor_class = cls._executors[node_type]
        return executor_class()

    @classmethod
    def clear(cls):
        """Utile pour réinitialiser le registre pendant les tests unitaire."""
        cls._executors.clear()