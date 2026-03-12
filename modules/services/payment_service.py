# -*- coding: utf-8 -*-
# applications/n8n_life/modules/services/payment_service.py

import stripe
import importlib
from typing import Dict, Any, Optional

import applications.reasoningframe.modules.engine.errors as engine_errors
import applications.reasoningframe.modules.services.provisioning_service as serv_provisioning

importlib.reload(engine_errors)
importlib.reload(serv_provisioning)

class PaymentService:
    """
    Gère la monétisation via Stripe. 
    Version ultra-sécurisée : comparaison de session, cast strict et isolation B2B.
    """

    def __init__(self, db: Any, stripe_api_key: str, user_id: Optional[int] = None):
        self.db = db
        self.user_id = user_id
        stripe.api_key = stripe_api_key

    # =========================================================================
    # 1. CRÉATION DU CHECKOUT
    # =========================================================================

    def create_checkout_session(self, template_id: int, success_url: str, cancel_url: str) -> str:
        if not self.user_id:
            raise engine_errors.N8nLifeEngineError("Utilisateur non identifié.", "ERR_UNAUTHORIZED")

        template = self.db(self.db.workflow_template.id == template_id).select().first()
        if not template or not template.is_published:
            raise engine_errors.N8nLifeEngineError("Template indisponible.", "ERR_TEMPLATE_NOT_AVAILABLE")

        if not template.provider_price_id:
            raise engine_errors.N8nLifeEngineError("Prix Stripe manquant.", "ERR_TEMPLATE_NO_PRICE")

        # Création de la commande interne
        order_id = self.db.payment_order.insert(
            user_id=self.user_id,
            template_id=template.id,
            status='pending',
            provider='stripe',
            provider_session_id=None,
            amount_cents=template.price_cents or 0,
            currency='EUR'
        )

        try:
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{'price': template.provider_price_id, 'quantity': 1}],
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                client_reference_id=str(self.user_id),
                # CORRECTION : cast explicite en string pour les metadata Stripe
                metadata={'order_id': str(order_id)} 
            )
            
            self.db(self.db.payment_order.id == order_id).update(provider_session_id=session.id)
            return session.url
            
        except Exception as e:
            self.db(self.db.payment_order.id == order_id).update(status='failed')
            raise engine_errors.N8nLifeEngineError(f"Erreur Stripe : {str(e)}", "ERR_STRIPE_ERROR")

    # =========================================================================
    # 2. VÉRIFICATION DU WEBHOOK
    # =========================================================================

    def verify_and_get_session(self, payload: bytes, sig_header: str, webhook_secret: str) -> Dict[str, Any]:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
            if event['type'] == 'checkout.session.completed':
                return event['data']['object']
            return {}
        except (stripe.error.SignatureVerificationError, ValueError):
            raise engine_errors.N8nLifeEngineError("Signature ou Payload invalide.", "ERR_STRIPE_BAD_WEBHOOK")

    # =========================================================================
    # 3. FULFILLMENT (Livraison métier sécurisée)
    # =========================================================================

    def fulfill_order_from_stripe(self, stripe_session: Dict[str, Any]) -> Dict[str, Any]:
        """
        Finalise l'achat avec triple vérification : ID de session, ID de commande et User ID.
        """
        # CORRECTION : Cast et validation stricte de l'order_id depuis metadata
        raw_order_id = stripe_session.get('metadata', {}).get('order_id')
        if not raw_order_id:
            raise engine_errors.N8nLifeEngineError("Métadonnée order_id manquante.", "ERR_STRIPE_MISSING_DATA")
        
        try:
            order_id = int(raw_order_id)
        except ValueError:
            raise engine_errors.N8nLifeEngineError("Format de order_id invalide.", "ERR_STRIPE_INVALID_DATA")

        # 1. Chargement de la commande
        order = self.db(self.db.payment_order.id == order_id).select().first()
        if not order:
            raise engine_errors.N8nLifeEngineError(f"Commande {order_id} introuvable.", "ERR_ORDER_NOT_FOUND")

        # CORRECTION : Comparaison stricte de l'ID de session Stripe pour éviter les injections
        if stripe_session.id != order.provider_session_id:
            raise engine_errors.N8nLifeEngineError("Discordance de session Stripe détectée.", "ERR_SECURITY_SESSION_MISMATCH")

        # 2. Idempotence
        if order.status == 'paid' or order.provisioned_workflow_id:
            return {"status": "already_processed", "workflow_id": order.provisioned_workflow_id}

        # 3. Vérification de sécurité B2B via client_reference_id
        try:
            client_ref_user_id = int(stripe_session.get('client_reference_id', 0))
        except ValueError:
            client_ref_user_id = 0

        if order.user_id != client_ref_user_id:
            raise engine_errors.N8nLifeEngineError("L'utilisateur payeur ne correspond pas à l'acheteur.", "ERR_SECURITY_USER_MISMATCH")

        # 4. Provisioning (On utilise l'order.template_id du backend)
        prov_service = serv_provisioning.ProvisioningService(db=self.db, user_id=order.user_id)
        
        try:
            # provision_after_payment lie déjà le workflow à la commande
            wf = prov_service.provision_after_payment(
                template_id=order.template_id,
                payment_order_id=order.id
            )
            
            # 5. Validation finale
            self.db(self.db.payment_order.id == order.id).update(status='paid')
            
            return {"status": "success", "workflow_id": wf.id}
            
        except Exception as e:
            self.db(self.db.payment_order.id == order.id).update(status='failed')
            raise engine_errors.N8nLifeEngineError(f"Échec de livraison technique : {str(e)}", "ERR_PROVISIONING_FAILED")