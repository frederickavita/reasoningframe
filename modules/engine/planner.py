# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/engine/planner.py

from typing import List, Set
import importlib

# On pointe vers TON application : reasoningframe
import applications.reasoningframe.modules.nodes.base as nodes_base
importlib.reload(nodes_base)

class ExecutionPlanner:
    """
    L'aiguilleur mathématique du DAG. 
    Calcule les dépendances et l'ordre d'exécution strict.
    """

    @staticmethod
    def get_upstream_nodes(wf_def: nodes_base.WorkflowDefinition, target_node_id: str) -> List[str]:
        """Trouve tous les nœuds 'Parents' d'un nœud cible."""
        upstream_nodes = set()
        for source_id, out_connections in wf_def.connections.items():
            for output_type, links in out_connections.items():
                for link in links:
                    if link.get('node') == target_node_id:
                        upstream_nodes.add(source_id)
                        
        return sorted(list(upstream_nodes))

    @staticmethod
    def get_ready_successors(wf_def: nodes_base.WorkflowDefinition, 
                             current_node_id: str, 
                             executed_nodes: Set[str]) -> List[str]:
        """
        LA MÉTHODE MANQUANTE :
        Trouve les enfants PRÊTS (tous les parents doivent être dans executed_nodes).
        """
        direct_successors = set()
        out_connections = wf_def.connections.get(current_node_id, {})
        
        for output_type, links in out_connections.items():
            for link in links:
                target_id = link.get('node')
                if target_id:
                    direct_successors.add(target_id)

        ready_successors = []
        for successor_id in sorted(list(direct_successors)):
            parents = ExecutionPlanner.get_upstream_nodes(wf_def, successor_id)
            # Un nœud est prêt si TOUS ses parents sont terminés
            if all(parent in executed_nodes for parent in parents):
                ready_successors.append(successor_id)

        return ready_successors

    @staticmethod
    def get_trigger_nodes(wf_def: nodes_base.WorkflowDefinition) -> List[str]:
        """Trouve les points d'entrée (nœuds sans parents)."""
        all_nodes = set(wf_def.nodes.keys())
        has_incoming = set()
        for source_id, out_connections in wf_def.connections.items():
            for output_type, links in out_connections.items():
                for link in links:
                    target_id = link.get('node')
                    if target_id:
                        has_incoming.add(target_id)
        return sorted(list(all_nodes - has_incoming))