# applications/reasoningframe/models/0_registry.py

from applications.reasoningframe.modules.nodes.registry import NodeRegistry
from applications.reasoningframe.modules.nodes.triggers.webhook import WebhookTriggerNode
from applications.reasoningframe.modules.nodes.triggers.cron import CronTriggerNode
from applications.reasoningframe.modules.nodes.actions.http_request import HttpRequestNode

# Nettoyage pour le hot-reload web2py
NodeRegistry.clear()

# Enregistrement des déclencheurs (Triggers)
NodeRegistry.register("trigger.webhook", WebhookTriggerNode)
NodeRegistry.register("trigger.cron", CronTriggerNode)

# Enregistrement des actions (Nodes classiques)
NodeRegistry.register("core.http", HttpRequestNode)