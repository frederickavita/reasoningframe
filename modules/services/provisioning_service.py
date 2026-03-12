# -*- coding: utf-8 -*-
# applications/n8n_life/modules/services/provisioning_service.py

import copy
import importlib
from typing import Dict, Any, Optional

# Imports stricts
import applications.reasoningframe.modules.engine.errors as engine_errors
import applications.reasoningframe.modules.services.workflow_service as serv_workflow

importlib.reload(engine_errors)
importlib.reload(serv_workflow)

class ProvisioningService:
    """
    Gère le passage d'un template (modèle partagé/commercial) vers un workflow privé utilisateur.
    Délègue la logique métier et le cycle de vie au WorkflowService.
    """

    def __init__(self, db: Any, user_id: int, workflow_service: Optional[Any] = None):
        self.db = db
        self.user_id = user_id
        self.workflow_service = workflow_service or serv_workflow.WorkflowService(db=self.db, user_id=self.user_id)

    # =========================================================================
    # LECTURE TEMPLATE
    # =========================================================================

    def load_template(self, template_id: int) -> Any:
        template_record = self.db(self.db.workflow_template.id == template_id).select().first()

        if not template_record:
            raise engine_errors.N8nLifeEngineError(
                message=f"Le template #{template_id} est introuvable.",
                error_code="ERR_TEMPLATE_NOT_FOUND"
            )
            
        if not getattr(template_record, 'is_published', False):
            raise engine_errors.N8nLifeEngineError(
                message=f"Le template #{template_id} n'est pas disponible pour le clonage.",
                error_code="ERR_TEMPLATE_NOT_AVAILABLE"
            )
            
        if not getattr(template_record, 'workflow_json', None):
            raise engine_errors.N8nLifeEngineError(
                message=f"Le template #{template_id} est invalide (JSON manquant).",
                error_code="ERR_TEMPLATE_INVALID"
            )
            
        return template_record

    # =========================================================================
    # SÉCURITÉ & NETTOYAGE
    # =========================================================================

    def sanitize_template_json_for_clone(self, template_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Nettoie le JSON du template avant de le copier chez l'utilisateur.
        Retire toutes les scories d'exécution et les éventuels secrets accidentels.
        """
        # CORRECTION : Fail-fast strict. On ne masque pas un template corrompu.
        if not isinstance(template_json, dict):
            raise engine_errors.N8nLifeEngineError(
                message="Le JSON du template est corrompu ou au mauvais format (doit être un dictionnaire).",
                error_code="ERR_TEMPLATE_INVALID"
            )

        # Deep copy pour ne pas altérer l'objet source en mémoire
        clean_json = copy.deepcopy(template_json)
        
        nodes = clean_json.get("nodes", [])
        
        # Gestion défensive des formats de la Factory
        nodes_iterable = nodes if isinstance(nodes, list) else nodes.values() if isinstance(nodes, dict) else []

        for node in nodes_iterable:
            if not isinstance(node, dict):
                continue
            
            suspect_keys = [
                "resolved_credentials", 
                "decrypted_secret", 
                "auth_headers_preview",
                "execution_history",
                "last_run_data"
            ]
            
            for key in suspect_keys:
                if key in node:
                    del node[key]
                    
            # Si le template utilisait un objet 'credentials' imbriqué contenant des valeurs concrètes, on le vide
            if "credentials" in node and isinstance(node["credentials"], dict):
                node["credentials"] = {}

        return clean_json

    # =========================================================================
    # PROVISIONING ACTIF
    # =========================================================================

    def provision_from_template(self, template_id: int, custom_name: Optional[str] = None) -> Any:
        template = self.load_template(template_id)
        
        safe_json = self.sanitize_template_json_for_clone(template.workflow_json)
        
        final_name = custom_name if custom_name and custom_name.strip() else f"{template.name}"
        
        # Délégation totale au WorkflowService (OFF par défaut, is_legitimately_acquired=True)
        cloned_workflow = self.workflow_service.create_workflow(
            name=final_name,
            workflow_json=safe_json,
            template_id=template.id,
            template_version_at_clone=getattr(template, 'version', 1),
            is_legitimately_acquired=True
        )
        
        return cloned_workflow

    def provision_after_payment(self, template_id: int, payment_order_id: Optional[int] = None, custom_name: Optional[str] = None) -> Any:
        # 1. On provisionne normalement
        wf = self.provision_from_template(template_id, custom_name)
        
        # 2. On lie la commande au workflow fraîchement créé
        if payment_order_id:
            # CORRECTION : Filtrage strict par user_id pour garantir l'isolation B2B totale
            updated = self.db(
                (self.db.payment_order.id == payment_order_id) &
                (self.db.payment_order.user_id == self.user_id)
            ).update(provisioned_workflow_id=wf.id)
            
            if not updated:
                # Logique défensive : Si la commande n'appartient pas à l'utilisateur, on refuse la transaction
                raise engine_errors.N8nLifeEngineError(
                    message=f"Commande de paiement #{payment_order_id} introuvable ou n'appartenant pas à cet utilisateur.",
                    error_code="ERR_PAYMENT_ORDER_NOT_FOUND"
                )
                
        return wf