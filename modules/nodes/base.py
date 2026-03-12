# -*- coding: utf-8 -*-
# applications/n8n_life/modules/nodes/base.py

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import importlib

import applications.reasoningframe.modules.engine.context as engine_context
importlib.reload(engine_context)

class NodeDefinition:
    """
    Représentation statique d'un nœud issue du JSON du Workflow.
    Totalement stupide : ne contient aucune logique, que de la donnée.
    """
    def __init__(self, 
                 node_id: str, 
                 node_type: str, 
                 parameters: Optional[Dict[str, Any]] = None, 
                 credential_key: Optional[str] = None):
        
        self.id = node_id
        self.type = node_type
        self.parameters = parameters or {}
        self.credential_key = credential_key

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NodeDefinition':
        """Reconstruit l'objet statique depuis le dictionnaire JSON."""
        return cls(
            node_id=data.get('id', ''),
            node_type=data.get('type', ''),
            parameters=data.get('parameters', {}),
            credential_key=data.get('credential_key')
        )

class WorkflowDefinition:
    """
    Représentation statique du graphe complet.
    MVP : Purement topologique (pas de meta/versioning pour l'instant).
    """
    def __init__(self, nodes: Dict[str, NodeDefinition], connections: Dict[str, Any]):
        self.nodes = nodes
        self.connections = connections or {}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowDefinition':
        """
        Reconstruit le graphe. 
        Transforme la liste de nœuds du JSON en un Dictionnaire indexé par node_id.
        """
        nodes_list = data.get('nodes', [])
        nodes_dict = {
            n_data.get('id'): NodeDefinition.from_dict(n_data) 
            for n_data in nodes_list if n_data.get('id')
        }
        
        return cls(
            nodes=nodes_dict,
            connections=data.get('connections', {})
        )

class NodeExecutor(ABC):
    """
    Le contrat fondamental de tous les nœuds (Stateless).
    Ne contient QUE l'interface abstraite. Aucun couplage avec les utilitaires métiers.
    """
    def __init__(self):
        pass

    @abstractmethod
    def execute(self, 
                node_def: NodeDefinition, 
                input_items: List[engine_context.Item], 
                context: engine_context.WorkflowContext, 
                security_provider: Any, 
                http_helper: Any) -> List[engine_context.Item]:
        """
        Le contrat d'exécution strict.
        :param node_def: La configuration du nœud (id, paramètres, credential_key).
        :param input_items: La donnée entrante (fusionnée par le ItemManager).
        :param context: Pour lire l'historique ou le payload d'origine.
        :param security_provider: Le service global de sécurité (accès aux secrets, résolution expressions...).
        :param http_helper: La façade pour les appels réseaux sortants.
        :return: La nouvelle liste d'Items à passer au nœud suivant.
        """
        pass