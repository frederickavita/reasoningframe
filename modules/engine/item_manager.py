# -*- coding: utf-8 -*-
# applications/n8n_life/modules/engine/item_manager.py

import copy
from typing import List, Dict
import importlib

# Imports web2py avec reload
import applications.reasoningframe.modules.engine.context as engine_context
importlib.reload(engine_context)


class ItemManager:
    """
    Gère la tuyauterie de la donnée entre les nœuds.
    Responsabilités : 
    1. Isoler la mémoire (Deepcopy) pour éviter les effets de bord.
    2. Aplatir les branches convergentes (Flatten pur).
    """

    @staticmethod
    def prepare_inputs(source_items: List[engine_context.Item], source_node_id: str) -> List[engine_context.Item]:
        """
        Clone les items d'un nœud source pour les fournir à un nœud cible.
        """
        prepared = []
        for index, item in enumerate(source_items):
            # 1. ISOLATION : Deepcopy strict pour la sécurité mémoire
            cloned_json = copy.deepcopy(item.json)
            cloned_binary = copy.deepcopy(item.binary)
            
            # 2. TRAÇABILITÉ (Paired Item)
            # RÈGLE MVP : On ne conserve que la provenance IMMÉDIATE (parent direct).
            # L'historique complet peut être reconstitué en remontant de parent en parent via le Context si besoin.
            new_paired_item = {
                "source_node_id": source_node_id,
                "source_index": index
            }
            
            # 3. ALIGNEMENT STRICT DU CONTRAT ITEM
            new_item = engine_context.Item(
                json=cloned_json, 
                binary=cloned_binary,
                paired_item=new_paired_item
            )
            
            new_item.meta = copy.deepcopy(item.meta)
            prepared.append(new_item)
            
        return prepared

    @staticmethod
    def merge_inputs(branches_data: Dict[str, List[engine_context.Item]]) -> List[engine_context.Item]:
        """
        Fusionne les items quand plusieurs branches convergent.
        
        SÉMANTIQUE : C'est un Flatten ordonné pur. Aucun "Join" ou agrégation métier.
        
        :param branches_data: Un dictionnaire sécurisé où la clé est l'ID du nœud parent, 
                              et la valeur est la liste de ses Items. Évite les listes parallèles fragiles.
        """
        merged_flat_list = []
        
        for parent_id, branch_items in branches_data.items():
            if branch_items:
                # On prépare (clone + trace) les items de ce parent spécifique
                prepared_branch = ItemManager.prepare_inputs(branch_items, parent_id)
                merged_flat_list.extend(prepared_branch)
                
        return merged_flat_list