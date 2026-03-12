# -*- coding: utf-8 -*-
# applications/reasoningframe/modules/engine/context.py

from enum import Enum
from typing import List, Dict, Any, Optional

# =========================================================================
# CONSTANTES D'ÉTAT (Le Contrat global)
# =========================================================================
class RunState(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

class StepState(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# =========================================================================
# 1. L'UNITÉ DE DONNÉE (ITEM)
# =========================================================================
class Item:
    """
    L'unité standard de donnée circulant entre les nœuds.
    Règle absolue : Toute entrée ou sortie de nœud DOIT être une List[Item].
    """
    def __init__(self, 
                 json: Dict[str, Any], 
                 paired_item: Optional[Dict[str, Any]] = None, 
                 binary: Optional[Dict[str, Any]] = None):
        
        self.json = json or {}
        self.binary = binary or {}
        self.paired_item = paired_item or {} 
        self.meta: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        """Sérialisation stricte pour le stockage dans la DB."""
        return {
            "json": self.json,
            "binary": self.binary,
            "paired_item": self.paired_item,
            "meta": self.meta
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Item':
        """Désérialisation."""
        item = cls(
            json=data.get("json", {}), 
            paired_item=data.get("paired_item", {}),
            binary=data.get("binary", {})
        )
        item.meta = data.get("meta", {})
        return item


# =========================================================================
# 2. LE CONTEXTE D'EXÉCUTION (WORKFLOW CONTEXT)
# =========================================================================
class WorkflowContext:
    """
    Conserve l'état complet et traçable d'un Run en mémoire. 
    """
    def __init__(self, trigger_items: List[Item]):
        # =====================================================================
        # LE VERROU DU CONTRAT EST ICI
        # La source de vérité immuable du déclenchement du workflow.
        # =====================================================================
        self.trigger_items: List[Item] = trigger_items or []
        
        # current_items est un cache pratique initialisé avec la vérité de départ
        self.current_items: List[Item] = self.trigger_items
        
        # La vraie source de vérité du DAG
        self.node_outputs: Dict[str, List[Item]] = {}  
        
        # Création de l'historique de step exigé par le Runner
        self.step_history: List[Dict[str, Any]] = []
        
        # Alignement total sur les Enums
        self.run_state: str = RunState.RUNNING.value           
        
        # Contrat strict pour les erreurs
        self.errors: List[Dict[str, Any]] = []    

    def update_node_output(self, node_id: str, items: List[Item]):
        """Enregistre le résultat d'un nœud dans la vérité du DAG."""
        self.node_outputs[node_id] = items
        self.current_items = items

    def get_node_output(self, node_id: str) -> List[Item]:
        """
        Fail-Fast si le nœud n'existe pas.
        Renvoie la liste des items SI ET SEULEMENT SI le nœud a été exécuté.
        """
        if node_id not in self.node_outputs:
            raise KeyError(f"Impossible de récupérer l'output : Le nœud '{node_id}' n'a pas été exécuté.")
        return self.node_outputs[node_id]

    def record_step(self, node_id: str, node_type: str, status: str, 
                    execution_time_ms: int, input_count: int, output_count: int, 
                    error_code: Optional[str] = None, error_message: Optional[str] = None,
                    execution_order: Optional[int] = None):
        """
        Implémente le contrat exact attendu par le Runner.
        Prépare les données pour la table SQL `workflow_run_step`.
        """
        # Auto-calcul de l'ordre d'exécution si non fourni par le Runner
        order = execution_order if execution_order is not None else len(self.step_history) + 1

        self.step_history.append({
            "node_id": node_id,
            "node_type": node_type,
            "execution_order": order,
            "status": status,
            "execution_time_ms": execution_time_ms,
            "input_count": input_count,
            "output_count": output_count,
            "error_code": error_code,
            "error_message": error_message
        })

    def halt_with_error(self, node_id: str, error_code: str, error_message: str):
        """Actionne le Fail-Fast : Stoppe le contexte et fige l'erreur."""
        self.run_state = RunState.FAILED.value
        self.errors.append({
            "node_id": node_id,
            "error_code": error_code,
            "error_message": error_message
        })

    def to_snapshot(self) -> Dict[str, Any]:
        """
        Snapshot enrichi pour la DB et le débogage.
        """
        return {
            "run_state": self.run_state,
            "total_steps_executed": len(self.step_history),
            "last_step": self.step_history[-1] if self.step_history else None,
            "errors": self.errors,
            # On stocke l'état courant (utile pour visualiser l'endroit du crash)
            "current_items": [item.to_dict() for item in self.current_items] 
        }