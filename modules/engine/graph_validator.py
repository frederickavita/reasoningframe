# -*- coding: utf-8 -*-
# applications/n8n_life/modules/engine/graph_validator.py

from typing import Set, List
import importlib

# CORRECTION 1 : Le chemin d'import exact
import applications.reasoningframe.modules.nodes.base as nodes_base
importlib.reload(nodes_base)

import applications.reasoningframe.modules.engine.errors as engine_errors
importlib.reload(engine_errors)


class GraphValidator:
    """
    S'assure que le graphe est à la fois mathématiquement sain (DAG) 
    ET fonctionnellement valide pour notre métier (Triggers, Reachability).
    """

    @staticmethod
    def validate(workflow_def: nodes_base.WorkflowDefinition, allow_multiple_triggers: bool = False):
        """Exécute toute la chaîne de validation. Fail-Fast au premier problème."""
        GraphValidator._check_not_empty(workflow_def)
        GraphValidator._check_connections_format(workflow_def)
        GraphValidator._check_missing_nodes(workflow_def)
        
        # On récupère les triggers pour les validations suivantes
        triggers = GraphValidator._check_triggers(workflow_def, allow_multiple_triggers)
        
        GraphValidator._check_reachability(workflow_def, triggers)
        GraphValidator._detect_cycles(workflow_def)

    @staticmethod
    def _check_not_empty(workflow_def: nodes_base.WorkflowDefinition):
        """CORRECTION 2 : Refuse un graphe vide."""
        if not workflow_def.nodes:
            raise engine_errors.GraphValidationError("Le workflow est vide (aucun nœud).")

    @staticmethod
    def _check_connections_format(workflow_def: nodes_base.WorkflowDefinition):
        """CORRECTION 5 : Vérifie la structure interne des connexions."""
        for source_id, out_connections in workflow_def.connections.items():
            if not isinstance(out_connections, dict):
                raise engine_errors.GraphValidationError(f"Format invalide pour les connexions du nœud '{source_id}'. Attendu : dict.")
            
            for output_type, links in out_connections.items():
                if not isinstance(links, list):
                    raise engine_errors.GraphValidationError(f"Format invalide pour la sortie '{output_type}' du nœud '{source_id}'. Attendu : list.")
                
                for link in links:
                    if not isinstance(link, dict):
                        raise engine_errors.GraphValidationError(f"Format de lien invalide dans le nœud '{source_id}'. Attendu : dict.")
                    
                    # CORRECTION 6 : Distingue "champ manquant" de "fantôme"
                    if 'node' not in link:
                        raise engine_errors.GraphValidationError(f"Un lien sortant du nœud '{source_id}' n'a pas de propriété 'node'.")

    @staticmethod
    def _check_missing_nodes(workflow_def: nodes_base.WorkflowDefinition):
        """Vérifie que les connexions ne pointent pas vers des nœuds inexistants."""
        for source_id, out_connections in workflow_def.connections.items():
            if source_id not in workflow_def.nodes:
                raise engine_errors.GraphValidationError(f"Connexion depuis un nœud source inexistant: '{source_id}'")
            
            for output_type, links in out_connections.items():
                for link in links:
                    target_id = link.get('node')
                    if target_id not in workflow_def.nodes:
                        raise engine_errors.GraphValidationError(f"Le nœud '{source_id}' pointe vers un nœud fantôme '{target_id}'")

    @staticmethod
    def _check_triggers(workflow_def: nodes_base.WorkflowDefinition, allow_multiple: bool) -> List[str]:
        """CORRECTION 3 : Vérifie la présence de nœuds déclencheurs."""
        triggers = []
        for node_id, node_def in workflow_def.nodes.items():
            if node_def.type.startswith('trigger.'):
                triggers.append(node_id)
        
        if not triggers:
            raise engine_errors.GraphValidationError("Le workflow ne contient aucun nœud de type 'trigger'. Il ne pourra jamais démarrer.")
            
        if not allow_multiple and len(triggers) > 1:
            raise engine_errors.GraphValidationError(f"Ce workflow contient {len(triggers)} triggers. Le MVP n'en autorise qu'un seul par graphe.")
            
        return triggers

    @staticmethod
    def _check_reachability(workflow_def: nodes_base.WorkflowDefinition, triggers: List[str]):
        """
        CORRECTION 4 : Vérifie que TOUS les nœuds sont atteignables 
        depuis au moins un trigger (pas d'orphelins).
        Algorithme : Breadth-First Search (BFS)
        """
        reachable_nodes: Set[str] = set()
        queue = triggers.copy()

        # On parcourt tout ce qui est accessible depuis les triggers
        while queue:
            current = queue.pop(0)
            if current not in reachable_nodes:
                reachable_nodes.add(current)
                
                # Ajouter les enfants à la file
                out_connections = workflow_def.connections.get(current, {})
                for output_type, links in out_connections.items():
                    for link in links:
                        queue.append(link.get('node'))

        # On vérifie s'il y a des nœuds dans le graphe qui n'ont pas été atteints
        all_nodes = set(workflow_def.nodes.keys())
        unreachable = all_nodes - reachable_nodes
        
        if unreachable:
            raise engine_errors.GraphValidationError(f"Le graphe contient des nœuds isolés inaccessibles depuis un trigger : {', '.join(unreachable)}")

    @staticmethod
    def _detect_cycles(workflow_def: nodes_base.WorkflowDefinition):
        """Détecte les boucles infinies via DFS."""
        visited = set()
        recursion_stack = set()

        def dfs(node_id: str):
            visited.add(node_id)
            recursion_stack.add(node_id)

            out_connections = workflow_def.connections.get(node_id, {})
            for output_type, links in out_connections.items():
                for link in links:
                    neighbor_id = link.get('node')
                    if neighbor_id not in visited:
                        dfs(neighbor_id)
                    elif neighbor_id in recursion_stack:
                        raise engine_errors.GraphValidationError(f"Cycle infini interdit détecté incluant le nœud : '{neighbor_id}'")

            recursion_stack.remove(node_id)

        for node_id in workflow_def.nodes.keys():
            if node_id not in visited:
                dfs(node_id)