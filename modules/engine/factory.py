# -*- coding: utf-8 -*-
# applications/n8n_life/modules/engine/factory.py

from typing import Dict, Any
import importlib

# Imports web2py avec reload
import applications.reasoningframe.modules.nodes.base as nodes_base
importlib.reload(nodes_base)

import applications.reasoningframe.modules.engine.errors as engine_errors
importlib.reload(engine_errors)


class WorkflowFactory:
    """
    Transforme le JSON brut (issu de la base de données) en objets d'architecture statique.
    Valide la forme, le typage, et garantit l'unicité des IDs.
    """
    
    @staticmethod
    def build_workflow(workflow_json: Dict[str, Any]) -> nodes_base.WorkflowDefinition:
        # 1. Validation de l'enveloppe globale
        if not workflow_json or not isinstance(workflow_json, dict):
            raise engine_errors.GraphValidationError("Erreur de parsing : Le payload JSON du workflow est invalide ou vide.")

        nodes_data = workflow_json.get('nodes', [])
        connections_data = workflow_json.get('connections', {})

        # 2. Validation stricte des types de base
        if not isinstance(nodes_data, list):
            raise engine_errors.GraphValidationError("Erreur de parsing : La propriété 'nodes' doit être une liste.")
        if not isinstance(connections_data, dict):
            raise engine_errors.GraphValidationError("Erreur de parsing : La propriété 'connections' doit être un dictionnaire.")

        # 3. Construction DIRECTE d'un dictionnaire indexé (Alignement avec le Runner/Planner)
        parsed_nodes: Dict[str, nodes_base.NodeDefinition] = {}
        
        for index, nd in enumerate(nodes_data):
            if not isinstance(nd, dict):
                raise engine_errors.GraphValidationError(f"Erreur de parsing : Le nœud à l'index {index} n'est pas un objet JSON valide.")
                
            # Clés obligatoires minimales pour exister
            node_id = nd.get('id')
            node_type = nd.get('type')
            
            if not node_id:
                raise engine_errors.GraphValidationError(f"Erreur de parsing : Le nœud à l'index {index} n'a pas d'identifiant ('id').")
            if not node_type:
                raise engine_errors.GraphValidationError(f"Erreur de parsing : Le nœud '{node_id}' n'a pas de type défini ('type').")

            # 4. SÉCURITÉ : Détection des doublons d'ID pour éviter l'écrasement silencieux
            if node_id in parsed_nodes:
                raise engine_errors.GraphValidationError(f"Erreur de construction : ID en doublon détecté ('{node_id}'). Chaque nœud doit avoir un ID strictement unique.")

            # Instanciation via le contrat propre de NodeDefinition
            parsed_nodes[node_id] = nodes_base.NodeDefinition.from_dict(nd)

        # 5. Construction de la Définition globale
        # Note : On s'assure que dans `nodes/base.py`, WorkflowDefinition.__init__ 
        # accepte bien `nodes: Dict[str, NodeDefinition]` et non plus une liste.
        return nodes_base.WorkflowDefinition(nodes=parsed_nodes, connections=connections_data)