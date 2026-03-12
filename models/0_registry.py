# -*- coding: utf-8 -*-
# applications/reasoningframe/models/0_registry.py

# 1. Import du Registry central
from applications.reasoningframe.modules.nodes.registry import NodeRegistry

# 2. Imports de tous les exécuteurs de nœuds validés
from applications.reasoningframe.modules.nodes.triggers.webhook import WebhookTriggerNode
from applications.reasoningframe.modules.nodes.triggers.cron import CronTriggerNode
from applications.reasoningframe.modules.nodes.transforms.set_fields import SetFieldsNode
from applications.reasoningframe.modules.nodes.transforms.filter import FilterNode

# (Ajoute tes futurs nœuds ici au fur et à mesure)
# from applications.reasoningframe.modules.nodes.actions.http_request import HttpRequestNode

# =========================================================================
# INITIALISATION DU CATALOGUE DES NŒUDS
# =========================================================================

# Nettoyage obligatoire pour éviter les doublons lors du hot-reload de Web2py
NodeRegistry.clear()

# Enregistrement des Déclencheurs (Triggers)
NodeRegistry.register("trigger.webhook", WebhookTriggerNode)
NodeRegistry.register("trigger.cron", CronTriggerNode)

# Enregistrement des Transformateurs (Transforms)
NodeRegistry.register("transform.set_fields", SetFieldsNode)
NodeRegistry.register("transform.filter", FilterNode)

# Enregistrement des Actions
# NodeRegistry.register("core.http", HttpRequestNode)