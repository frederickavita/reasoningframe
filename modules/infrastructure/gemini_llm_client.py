# -*- coding: utf-8 -*-

import json
import re
import unicodedata

from google import genai

from applications.reasoningframe.modules.application.ports import LLMEnrichmentPort


class GeminiLLMClientError(Exception):
    """Raised when Gemini enrichment fails."""
    pass


class GeminiLLMClient(LLMEnrichmentPort):
    """
    Gemini-based implementation of LLMEnrichmentPort.

    Uses Gemini native structured output with JSON schema when possible,
    plus a defensive fallback parser.

    Final returned contract (app-normalized):
    {
        "business_summary": "...",
        "qualification_explanation": "...",
        "fit_confidence": "high|medium|low",
        "llm_business_type": "...",
        "llm_offer_fit": "...",
        "outreach_angle": "...",
        "email_framework_used": "reply_first_micro_pas",
        "email_subject": "...",
        "email_opening_line": "...",
        "email_draft": "...",
        "derived_signals": [
            {
                "signal_type": "english_snake_case_label",
                "signal_value": "...",
                "polarity": "positive|negative|unknown",
                "source_kind": "llm",
                "confidence": 0.0-1.0,
                "reason": "..."
            }
        ],
        "cold_call_framework_used": "permission_problem_binary_soft_close",
        "cold_call_opening": "...",
        "cold_call_problem_hook": "...",
        "cold_call_binary_question": "...",
        "cold_call_soft_close": "...",
        "cold_call_script": "...",
        "contact_name": "...",
        "contact_role": "...",
        "contact_name_confidence": "high|medium|low",
        "address_text": "...",
        "address_confidence": "high|medium|low",
        "contact_evidence_text": "...",
        "llm_model_used": "gemini-2.5-flash-lite"
    }
    """

    DEFAULT_MODEL = "models/gemini-2.5-flash-lite"
    DEFAULT_MAX_SITE_TEXT_CHARS = 12000
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MAX_DERIVED_SIGNALS = 3

    def __init__(self, api_key, model_name=None, max_site_text_chars=None, temperature=None):
        if not api_key:
            raise GeminiLLMClientError("Gemini API key is missing.")

        self.api_key = api_key
        self.model_name = model_name or self.DEFAULT_MODEL
        self.max_site_text_chars = max_site_text_chars or self.DEFAULT_MAX_SITE_TEXT_CHARS
        self.temperature = self.DEFAULT_TEMPERATURE if temperature is None else temperature
        self.client = genai.Client(api_key=self.api_key)

    def enrich_prospect(self, site_text, business_context):
        site_text = self._normalize_text(site_text)
        site_text = site_text[:self.max_site_text_chars]

        if not site_text:
            raise GeminiLLMClientError("site_text is required for enrichment.")

        business_context = business_context or {}

        system_instruction = self._build_system_instruction()
        user_prompt = self._build_user_prompt(site_text, business_context)
        schema = self._build_response_schema()

        raw_text = ""
        parsed = None

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config={
                    "system_instruction": system_instruction,
                    "temperature": self.temperature,
                    "response_mime_type": "application/json",
                    "response_json_schema": schema,
                },
            )
            raw_text = self._extract_response_text(response)
            parsed = self._parse_json_response(raw_text)
        except Exception as e:
            try:
                fallback_prompt = user_prompt + "\n\nReturn only one valid JSON object."
                fallback_response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=fallback_prompt,
                    config={
                        "system_instruction": system_instruction,
                        "temperature": self.temperature,
                        "response_mime_type": "application/json",
                    },
                )
                raw_text = self._extract_response_text(fallback_response)
                parsed = self._parse_json_response(raw_text)
            except Exception as fallback_e:
                raise GeminiLLMClientError(
                    "Gemini request failed. Structured output error: %s ; fallback error: %s"
                    % (e, fallback_e)
                )

        normalized = self._normalize_output(parsed, business_context=business_context)
        normalized["llm_model_used"] = self._normalize_model_name(self.model_name)
        return normalized

    # --------------------------------------------------
    # Prompt building
    # --------------------------------------------------

    def _build_system_instruction(self):
        return """
<role>
You are an expert B2B prospect research analyst, reply-first cold email drafter, and cold call opener assistant.
</role>

<core_principle>
The user's offer is the main lens.
Prioritize:
1. offer-fit angle
2. visible public signal-based angle
3. website-based angle only when explicitly relevant to the offer
Do not default to generic website criticism.
</core_principle>

<factual_policy>
Use explicit public evidence for factual claims.
Do not invent facts, internal priorities, budgets, metrics, team structure, technical stack, or pain points.
Allow cautious low inference only for:
- derived_signals
- outreach_angle
- email angle
- cold call hook
When using low inference:
- phrase it cautiously
- never present it as certainty
- keep it tightly tied to visible evidence
</factual_policy>

<qualification_policy>
Use:
- high = multiple explicit strong signals tied to the user's offer
- medium = at least one direct useful signal and plausible offer relevance
- low = weak, ambiguous, generic, or insufficiently supported fit
If truly uncertain, prefer low.
</qualification_policy>

<email_policy>
Generate a B2B first-touch cold email draft.
Goal: start a conversation, not sell the full service.

Style:
- plain-text feel
- conversational
- short
- professional
- one idea
- one CTA
- reply-first

Subject:
- concrete
- short
- ideally 3 to 7 words
- ideally 20 to 40 characters
- avoid hype and generic marketing phrasing

Body:
- ideally 50 to 80 words
- maximum 90 words
- maximum 4 sentences

Preferred structure:
1. grounded context anchor
2. why the user's offer may be relevant
3. low-friction reply CTA
</email_policy>

<cold_call_policy>
Generate a short B2B cold call opener.
Goal: earn permission, open dialogue, and create a next step.

Style:
- calm
- direct
- respectful
- short
- professional
- low pressure

Structure:
1. honest opener
2. relevant problem hook
3. binary question when possible
4. soft close

The goal is not to sell on the call.
</cold_call_policy>

<contact_policy>
Only extract contact_name, contact_role, and address_text if explicitly present.
Never infer a name from an email address.
Never infer a role without explicit evidence.
Never reconstruct a partial address.
</contact_policy>

<derived_signal_policy>
For derived_signals:
- signal_type must always be an English snake_case machine label
- signal_value must be written in the selected output language
- reason must be written in the selected output language
- do not leave secondary fields in English when the selected output language is French
- do not leave secondary fields in French when the selected output language is English
</derived_signal_policy>

<format_policy>
Return only the JSON object matching the schema.
No markdown.
No extra commentary.
No extra keys.
</format_policy>

<few_shot_examples>
%s
</few_shot_examples>
""".strip() % self._build_few_shot_examples_xml()

    def _build_few_shot_examples_xml(self):
        examples = [
            {
                "input": {
                    "niche": "dentists",
                    "city": "Paris",
                    "offer": "website redesign and conversion optimization",
                    "output_language": "en",
                    "signals": [
                        {
                            "signal_type": "booking_detected",
                            "signal_value": "online booking visible",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.95,
                            "reason": "Online booking is visible on the site."
                        }
                    ],
                    "website_text": (
                        "Modern dental clinic in Paris. Patients can book appointments online. "
                        "The clinic offers cosmetic dentistry, implants, and emergency dental care. "
                        "Practice Director: Dr. Claire Martin. Address: 28 rue Meslay, 75003 Paris, France. "
                        "Contact: contact@clinic-example.com"
                    )
                },
                "output": {
                    "business_summary": "Dental clinic in Paris offering cosmetic dentistry, implants, and emergency care. Online booking is visible on the site.",
                    "qualification_explanation": "Strong fit because the business is local, service-based, and explicitly relies on online booking.",
                    "fit_confidence": "high",
                    "llm_business_type": "dental clinic",
                    "llm_offer_fit": "Website redesign and conversion optimization is relevant because the site explicitly supports online booking, so clarity and booking completion matter.",
                    "outreach_angle": "The visible booking flow suggests conversion clarity and patient journey optimization is relevant here.",
                    "email_framework_used": "reply_first_micro_pas",
                    "email_subject": "booking flow question",
                    "email_opening_line": "Noticed your clinic already supports online booking.",
                    "email_draft": "Noticed your clinic already supports online booking. For practices like yours, small changes to page structure and booking flow can sometimes make it easier for more visitors to complete booking. Open to a quick look at that?",
                    "derived_signals": [
                        {
                            "signal_type": "booking_intent_visible",
                            "signal_value": "online booking flow",
                            "polarity": "positive",
                            "source_kind": "llm",
                            "confidence": 0.82,
                            "reason": "The site explicitly shows online booking, which makes conversion-related improvement relevant."
                        }
                    ],
                    "cold_call_framework_used": "permission_problem_binary_soft_close",
                    "cold_call_opening": "Hi — this is a cold call, but I’ll be brief.",
                    "cold_call_problem_hook": "I’m reaching out because clinics with visible booking flows often focus next on improving how many visitors complete booking.",
                    "cold_call_binary_question": "Is the bigger priority right now getting more qualified traffic, or improving booking completion from the traffic you already have?",
                    "cold_call_soft_close": "If that is relevant, we could look at it in 10 minutes next week.",
                    "cold_call_script": "Hi — this is a cold call, but I’ll be brief. I’m reaching out because clinics with visible booking flows often focus next on improving how many visitors complete booking. Is the bigger priority right now getting more qualified traffic, or improving booking completion from the traffic you already have? If that is relevant, we could look at it in 10 minutes next week.",
                    "contact_name": "Dr. Claire Martin",
                    "contact_role": "Practice Director",
                    "contact_name_confidence": "high",
                    "address_text": "28 rue Meslay, 75003 Paris, France",
                    "address_confidence": "high",
                    "contact_evidence_text": "Practice Director: Dr. Claire Martin. Address: 28 rue Meslay, 75003 Paris, France."
                }
            },
            {
                "input": {
                    "niche": "agences digitales",
                    "city": "Lyon",
                    "offer": "sous-traitance logicielle white-label pour absorber la charge projet",
                    "output_language": "fr",
                    "signals": [
                        {
                            "signal_type": "multi_service_delivery",
                            "signal_value": "saas ecommerce mobile backend qa support",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.88,
                            "reason": "Le site liste plusieurs capacités techniques de livraison."
                        }
                    ],
                    "website_text": (
                        "Agence digitale à Lyon. Nous concevons et développons des plateformes SaaS, "
                        "des sites e-commerce, des applications mobiles, des systèmes backend et des "
                        "workflows QA pour des clients en France et en Europe."
                    )
                },
                "output": {
                    "business_summary": "Agence digitale à Lyon livrant des projets SaaS, e-commerce, mobile, backend et QA pour des clients en France et en Europe.",
                    "qualification_explanation": "Adéquation moyenne car l'agence livre plusieurs types de projets techniques pour des clients, ce qui rend une capacité externe potentiellement pertinente, sans besoin explicite visible.",
                    "fit_confidence": "medium",
                    "llm_business_type": "agence digitale",
                    "llm_offer_fit": "La sous-traitance logicielle white-label peut être pertinente car l'agence gère plusieurs flux de delivery et peut parfois avoir besoin de capacité externe.",
                    "outreach_angle": "La diversité des projets techniques suggère qu'un renfort externe peut être pertinent lors des pics de charge.",
                    "email_framework_used": "reply_first_micro_pas",
                    "email_subject": "capacité de delivery",
                    "email_opening_line": "J'ai vu votre agence en passant en revue des équipes qui livrent plusieurs types de projets.",
                    "email_draft": "J'ai vu votre agence en passant en revue des équipes qui livrent plusieurs types de projets. Quand une agence gère du SaaS, du mobile, du backend et de la QA pour des clients, une capacité externe en white-label peut parfois aider à absorber la charge. Souhaitez-vous un rapide aperçu de la façon dont nous intervenons ?",
                    "derived_signals": [
                        {
                            "signal_type": "broad_delivery_scope",
                            "signal_value": "plusieurs domaines techniques livrés",
                            "polarity": "positive",
                            "source_kind": "llm",
                            "confidence": 0.76,
                            "reason": "Le site montre explicitement plusieurs domaines de delivery, ce qui rend un soutien externe plausible."
                        }
                    ],
                    "cold_call_framework_used": "permission_problem_binary_soft_close",
                    "cold_call_opening": "Bonjour — c'est un appel à froid, mais je serai bref.",
                    "cold_call_problem_hook": "Je vous appelle car les agences qui livrent sur plusieurs flux techniques rencontrent parfois des tensions de capacité ou de couverture spécialisée.",
                    "cold_call_binary_question": "Le sujet principal est-il plutôt la capacité de delivery, ou la recherche des bons spécialistes quand la charge monte ?",
                    "cold_call_soft_close": "Si c'est pertinent, nous pourrions comparer nos approches pendant 10 minutes la semaine prochaine.",
                    "cold_call_script": "Bonjour — c'est un appel à froid, mais je serai bref. Je vous appelle car les agences qui livrent sur plusieurs flux techniques rencontrent parfois des tensions de capacité ou de couverture spécialisée. Le sujet principal est-il plutôt la capacité de delivery, ou la recherche des bons spécialistes quand la charge monte ? Si c'est pertinent, nous pourrions comparer nos approches pendant 10 minutes la semaine prochaine.",
                    "contact_name": "",
                    "contact_role": "",
                    "contact_name_confidence": "low",
                    "address_text": "",
                    "address_confidence": "low",
                    "contact_evidence_text": ""
                }
            },
            {
                "input": {
                    "niche": "entreprises de services",
                    "city": "Lille",
                    "offer": "design de marque et refonte de site web",
                    "output_language": "fr",
                    "signals": [],
                    "website_text": (
                        "Fournisseur d'équipements industriels. Catalogue produits, fiches techniques, "
                        "certifications et informations sur le réseau de distributeurs."
                    )
                },
                "output": {
                    "business_summary": "Fournisseur d'équipements industriels avec catalogue produits, fiches techniques, certifications et informations distributeurs.",
                    "qualification_explanation": "Adéquation faible car les informations publiques ne montrent pas de lien clair avec l'offre de design de marque et de refonte de site.",
                    "fit_confidence": "low",
                    "llm_business_type": "fournisseur d'équipements industriels",
                    "llm_offer_fit": "Il existe peu de preuves publiques indiquant que le design de marque et la refonte de site soient une priorité actuelle pour ce prospect.",
                    "outreach_angle": "Les informations publiques sont trop limitées pour soutenir un angle de prospection fort et spécifique pour cette offre.",
                    "email_framework_used": "reply_first_micro_pas",
                    "email_subject": "question rapide",
                    "email_opening_line": "J'ai jeté un coup d'œil rapide à votre entreprise.",
                    "email_draft": "J'ai jeté un coup d'œil rapide à votre entreprise. Il pourrait y avoir un angle pertinent avec le type de missions que je fais, mais les informations publiques sont limitées, donc je préfère rester prudent. Serait-il utile que j'envoie une très courte note sur les points où je pourrais être pertinent ?",
                    "derived_signals": [],
                    "cold_call_framework_used": "permission_problem_binary_soft_close",
                    "cold_call_opening": "Bonjour — ceci est un appel à froid, et je serai bref.",
                    "cold_call_problem_hook": "Je vous contacte prudemment car je n'ai pas pu confirmer, à partir des informations publiques, si la clarté de la marque ou la présentation du site sont une priorité active pour votre entreprise.",
                    "cold_call_binary_question": "Est-ce simplement pas une priorité pour le moment, ou est-ce un sujet qui revient occasionnellement quand vous revoyez la présentation de l'entreprise ?",
                    "cold_call_soft_close": "S'il y a une pertinence, nous pourrions en parler brièvement lors d'un suivi.",
                    "cold_call_script": "Bonjour — ceci est un appel à froid, et je serai bref. Je vous contacte prudemment car je n'ai pas pu confirmer, à partir des informations publiques, si la clarté de la marque ou la présentation du site sont une priorité active pour votre entreprise. Est-ce simplement pas une priorité pour le moment, ou est-ce un sujet qui revient occasionnellement quand vous revoyez la présentation de l'entreprise ? S'il y a une pertinence, nous pourrions en parler brièvement lors d'un suivi.",
                    "contact_name": "",
                    "contact_role": "",
                    "contact_name_confidence": "low",
                    "address_text": "",
                    "address_confidence": "low",
                    "contact_evidence_text": ""
                }
            }
        ]

        blocks = []
        for i, example in enumerate(examples, start=1):
            blocks.append(
                "<example index=\"%s\">\n<input>\n%s\n</input>\n<output>\n%s\n</output>\n</example>" % (
                    i,
                    json.dumps(example["input"], ensure_ascii=False, indent=2),
                    json.dumps(example["output"], ensure_ascii=False, indent=2),
                )
            )

        return "\n\n".join(blocks)

    def _build_user_prompt(self, site_text, business_context):
        niche = self._normalize_text(business_context.get("niche", ""))
        city = self._normalize_text(business_context.get("city", ""))
        offer = self._normalize_text(business_context.get("offer", ""))
        output_language = self._normalize_text(business_context.get("output_language", ""))

        signals = business_context.get("signals", [])
        if not isinstance(signals, list):
            signals = []

        signals_json = json.dumps(signals, ensure_ascii=False, indent=2)
        site_text = self._normalize_text(site_text)[:self.max_site_text_chars]

        return """
<user_target_context>
<niche>%s</niche>
<city>%s</city>
<offer>%s</offer>
<output_language>%s</output_language>
</user_target_context>

<existing_signals>
%s
</existing_signals>

<website_text>
%s
</website_text>

<task>
Analyze whether this business looks like a relevant prospect for the user's offer.

Then return a JSON object that:
- summarizes the business
- explains the qualification level
- estimates fit conservatively
- explains how the user's offer may fit
- proposes one credible outreach angle
- generates one short reply-first cold email
- generates one short cold call opener script
- includes only cautious derived signals when justified
- includes contact details only when explicitly present

Based on the information above, return only the JSON object matching the provided schema.
</task>
""" % (niche, city, offer, output_language, signals_json, site_text)

    def _build_response_schema(self):
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "business_summary": {
                    "type": "string",
                    "description": "A short factual 1-2 sentence summary of what the business does, grounded only in visible website text."
                },
                "qualification_explanation": {
                    "type": "string",
                    "description": "A short explanation of why this prospect is high, medium, or low fit for the user's offer. Must stay grounded and cautious."
                },
                "fit_confidence": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Overall fit confidence. Use high only with multiple explicit strong signals. Use low when evidence is weak or ambiguous."
                },
                "llm_business_type": {
                    "type": "string",
                    "description": "Literal business type using source-near wording such as 'dental clinic' or 'digital product agency'."
                },
                "llm_offer_fit": {
                    "type": "string",
                    "description": "Short explanation of how the user's offer fits or may fit this business. Use stronger wording when directly supported, and cautious wording when based on weak inference."
                },
                "outreach_angle": {
                    "type": "string",
                    "description": "One credible first-contact angle, prioritized from offer-fit first, then public signals, then website angle only when explicitly relevant."
                },
                "email_framework_used": {
                    "type": "string",
                    "enum": ["reply_first_micro_pas"],
                    "description": "Framework label for the email generation strategy."
                },
                "email_subject": {
                    "type": "string",
                    "description": "Short conversational subject line for a first-touch B2B email. Prefer specific and plain wording."
                },
                "email_opening_line": {
                    "type": "string",
                    "description": "First sentence of the email. Should act as a grounded context anchor and work well as preview text."
                },
                "email_draft": {
                    "type": "string",
                    "description": "Very short reply-first B2B cold email draft. Plain-text feel, one idea, one CTA, no hype, no fake personalization."
                },
                "derived_signals": {
                    "type": "array",
                    "description": "Up to 3 cautious low-inference signals derived from explicit evidence. signal_type must stay in English snake_case. signal_value and reason must follow the selected output language.",
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "signal_type": {
                                "type": "string",
                                "description": "English snake_case machine label for the derived signal."
                            },
                            "signal_value": {
                                "type": "string",
                                "description": "Human-readable signal value in the selected output language."
                            },
                            "polarity": {
                                "type": "string",
                                "enum": ["positive", "negative", "unknown"],
                                "description": "Signal polarity."
                            },
                            "source_kind": {
                                "type": "string",
                                "enum": ["llm"],
                                "description": "Always 'llm' for derived signals generated by the model."
                            },
                            "confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                                "description": "Confidence score between 0.0 and 1.0 for the derived signal."
                            },
                            "reason": {
                                "type": "string",
                                "description": "Short explanation tied to explicit evidence, in the selected output language."
                            },
                        },
                        "required": [
                            "signal_type",
                            "signal_value",
                            "polarity",
                            "source_kind",
                            "confidence",
                            "reason",
                        ],
                    },
                },
                "cold_call_framework_used": {
                    "type": "string",
                    "enum": ["permission_problem_binary_soft_close"],
                    "description": "Framework label for the cold call generation strategy."
                },
                "cold_call_opening": {
                    "type": "string",
                    "description": "Short honest opener for a B2B cold call."
                },
                "cold_call_problem_hook": {
                    "type": "string",
                    "description": "A short, grounded reason for calling tied to the user's offer and visible prospect context."
                },
                "cold_call_binary_question": {
                    "type": "string",
                    "description": "A short either-or style question that reduces cognitive load and opens dialogue."
                },
                "cold_call_soft_close": {
                    "type": "string",
                    "description": "A low-friction next step proposal, not a hard sell."
                },
                "cold_call_script": {
                    "type": "string",
                    "description": "A concise spoken cold call script combining opener, hook, binary question, and soft close."
                },
                "contact_name": {
                    "type": "string",
                    "description": "Explicitly visible contact name only. Empty string if not explicitly present."
                },
                "contact_role": {
                    "type": "string",
                    "description": "Explicitly visible contact role only. Empty string if not explicitly present."
                },
                "contact_name_confidence": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Confidence in the extracted contact name."
                },
                "address_text": {
                    "type": "string",
                    "description": "Explicitly visible address only. Empty string if not explicitly present."
                },
                "address_confidence": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Confidence in the extracted address."
                },
                "contact_evidence_text": {
                    "type": "string",
                    "description": "Short supporting excerpt for an explicitly extracted contact field. Empty string if no valid evidence exists."
                },
            },
            "required": [
                "business_summary",
                "qualification_explanation",
                "fit_confidence",
                "llm_business_type",
                "llm_offer_fit",
                "outreach_angle",
                "email_framework_used",
                "email_subject",
                "email_opening_line",
                "email_draft",
                "derived_signals",
                "cold_call_framework_used",
                "cold_call_opening",
                "cold_call_problem_hook",
                "cold_call_binary_question",
                "cold_call_soft_close",
                "cold_call_script",
                "contact_name",
                "contact_role",
                "contact_name_confidence",
                "address_text",
                "address_confidence",
                "contact_evidence_text",
            ],
        }

    # --------------------------------------------------
    # Response parsing
    # --------------------------------------------------

    def _extract_response_text(self, response):
        text = getattr(response, "text", None)
        if text:
            return text.strip()

        try:
            candidates = []
            for cand in getattr(response, "candidates", []) or []:
                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", []) or []
                for part in parts:
                    part_text = getattr(part, "text", None)
                    if part_text:
                        candidates.append(part_text)
            if candidates:
                return "\n".join(candidates).strip()
        except Exception:
            pass

        raise GeminiLLMClientError("Gemini returned no text content.")

    def _parse_json_response(self, raw_text):
        raw_text = (raw_text or "").strip()

        if not raw_text:
            raise GeminiLLMClientError("Gemini returned empty text.")

        raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
        raw_text = re.sub(r"^```\s*", "", raw_text, flags=re.IGNORECASE)
        raw_text = re.sub(r"\s*```$", "", raw_text)

        try:
            return json.loads(raw_text)
        except ValueError:
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = raw_text[start:end + 1]
                try:
                    return json.loads(candidate)
                except ValueError:
                    pass

        raise GeminiLLMClientError("Gemini returned invalid JSON: %s" % raw_text[:1000])

    # --------------------------------------------------
    # Normalization helpers
    # --------------------------------------------------

    def _normalize_text(self, value):
        if value is None:
            return ""
        value = str(value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _normalize_confidence_label(self, value, default_value):
        value = self._normalize_text(value).lower()
        if value not in ("low", "medium", "high"):
            return default_value
        return value

    def _normalize_signal_polarity(self, value):
        value = self._normalize_text(value).lower()
        if value not in ("positive", "negative", "unknown"):
            return "unknown"
        return value

    def _normalize_signal_confidence(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.5

        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    def _normalize_model_name(self, value):
        value = self._normalize_text(value)
        if value.startswith("models/"):
            return value[len("models/"):]
        return value

    def _normalize_business_type(self, value):
        value = self._normalize_text(value)
        return value.lower()

    def _normalize_contact_evidence_text(self, value, parsed):
        value = self._normalize_text(value)

        contact_name = self._normalize_text(parsed.get("contact_name", ""))
        contact_role = self._normalize_text(parsed.get("contact_role", ""))
        address_text = self._normalize_text(parsed.get("address_text", ""))

        if not contact_name and not contact_role and not address_text:
            return ""

        if len(value) > 500:
            value = value[:500].strip()

        return value

    def _normalize_email_framework_used(self, value):
        value = self._normalize_text(value)
        if value != "reply_first_micro_pas":
            return "reply_first_micro_pas"
        return value

    def _normalize_cold_call_framework_used(self, value):
        value = self._normalize_text(value)
        if value != "permission_problem_binary_soft_close":
            return "permission_problem_binary_soft_close"
        return value

    def _normalize_output_language(self, value):
        value = self._normalize_text(value).lower()
        if value.startswith("fr"):
            return "fr"
        if value.startswith("en"):
            return "en"
        return "en"

    def _sanitize_signal_type(self, value):
        """
        Always return an English-like machine label in snake_case.
        We do not try to translate; we normalize to a stable machine-readable key.
        """
        value = self._normalize_text(value).lower()

        if not value:
            return "llm_signal"

        value = unicodedata.normalize("NFKD", value)
        value = "".join(ch for ch in value if not unicodedata.combining(ch))
        value = re.sub(r"[^a-z0-9]+", "_", value)
        value = re.sub(r"_+", "_", value).strip("_")

        if not value:
            return "llm_signal"

        return value

    def _is_likely_french(self, text):
        text = " " + self._normalize_text(text).lower() + " "

        if not text.strip():
            return True

        french_markers = [
            " le ", " la ", " les ", " de ", " des ", " du ", " un ", " une ",
            " pour ", " votre ", " vous ", " sur ", " avec ", " est ", " au ",
            " aux ", " dans ", " que ", " qui ", " plus ", " peut ", " cela ",
            " rendez-vous ", " devis ", " agence ", " cabinet ", " entreprise ",
            " formulaire ", " priorité ", " clients ", " pertinence ",
            " réservation ", " suivi ", " qualifié ", " prospect "
        ]

        english_markers = [
            " the ", " and ", " for ", " with ", " this ", " that ", " your ",
            " you ", " open to ", " quick ", " question ", " booking ", " traffic ",
            " lead ", " call ", " business ", " relevant ", " delivery ", " support ",
            " multiple forms and appointment requests ", " online booking flow "
        ]

        fr_hits = sum(1 for m in french_markers if m in text)
        en_hits = sum(1 for m in english_markers if m in text)

        return fr_hits >= en_hits

    def _is_likely_english(self, text):
        text = " " + self._normalize_text(text).lower() + " "

        if not text.strip():
            return True

        english_markers = [
            " the ", " and ", " for ", " with ", " this ", " that ", " your ",
            " you ", " open to ", " quick ", " question ", " booking ", " traffic ",
            " lead ", " call ", " business ", " relevant ", " delivery ", " support ",
            " multiple forms ", " appointment requests ", " follow-up "
        ]

        french_markers = [
            " le ", " la ", " les ", " de ", " des ", " du ", " rendez-vous ",
            " devis ", " entreprise ", " agence ", " cabinet ", " rapide ",
            " serait-il ", " pourriez-vous ", " en discuter ", " semaine prochaine ",
            " réservation ", " suivi ", " priorité ", " formulaire "
        ]

        en_hits = sum(1 for m in english_markers if m in text)
        fr_hits = sum(1 for m in french_markers if m in text)

        return en_hits >= fr_hits

    def _is_text_compatible_with_output_language(self, text, output_language):
        text = self._normalize_text(text)
        if not text:
            return True

        output_language = self._normalize_output_language(output_language)

        if output_language == "fr":
            return self._is_likely_french(text)

        return self._is_likely_english(text)

    def _normalize_output(self, parsed, business_context=None):
        if not isinstance(parsed, dict):
            raise GeminiLLMClientError("Parsed Gemini response must be a dictionary.")

        business_context = business_context or {}
        output_language = self._normalize_output_language(
            business_context.get("output_language", "en")
        )

        existing_signals = business_context.get("signals", [])
        if not isinstance(existing_signals, list):
            existing_signals = []

        existing_signal_keys = set()
        for sig in existing_signals:
            if isinstance(sig, dict):
                existing_signal_keys.add((
                    self._normalize_text(sig.get("signal_type", "")).lower(),
                    self._normalize_text(sig.get("signal_value", "")).lower(),
                ))

        derived_signals = parsed.get("derived_signals", [])
        if not isinstance(derived_signals, list):
            derived_signals = []

        normalized_signals = []
        seen_signal_keys = set()

        for item in derived_signals:
            if not isinstance(item, dict):
                continue

            signal_type = self._sanitize_signal_type(item.get("signal_type", ""))
            signal_value = self._normalize_text(item.get("signal_value", ""))
            signal_reason = self._normalize_text(item.get("reason", ""))

            signal_key = (signal_type.lower(), signal_value.lower())

            if signal_key in seen_signal_keys:
                continue

            if signal_key in existing_signal_keys:
                continue

            # Critical language guard for secondary fields
            if not self._is_text_compatible_with_output_language(signal_value, output_language):
                continue

            if not self._is_text_compatible_with_output_language(signal_reason, output_language):
                continue

            normalized_signals.append({
                "signal_type": signal_type,
                "signal_value": signal_value,
                "polarity": self._normalize_signal_polarity(item.get("polarity", "unknown")),
                "source_kind": "llm",
                "confidence": self._normalize_signal_confidence(item.get("confidence", 0.5)),
                "reason": signal_reason[:300],
            })
            seen_signal_keys.add(signal_key)

            if len(normalized_signals) >= self.DEFAULT_MAX_DERIVED_SIGNALS:
                break

        parsed["address_text"] = self._normalize_text(parsed.get("address_text", ""))
        parsed["contact_name"] = self._normalize_text(parsed.get("contact_name", ""))
        parsed["contact_role"] = self._normalize_text(parsed.get("contact_role", ""))

        return {
            "business_summary": self._normalize_text(parsed.get("business_summary", ""))[:400],
            "qualification_explanation": self._normalize_text(parsed.get("qualification_explanation", ""))[:400],
            "fit_confidence": self._normalize_confidence_label(
                parsed.get("fit_confidence", "low"), "low"
            ),
            "llm_business_type": self._normalize_business_type(parsed.get("llm_business_type", ""))[:120],
            "llm_offer_fit": self._normalize_text(parsed.get("llm_offer_fit", ""))[:400],
            "outreach_angle": self._normalize_text(parsed.get("outreach_angle", ""))[:400],
            "email_framework_used": self._normalize_email_framework_used(
                parsed.get("email_framework_used", "reply_first_micro_pas")
            ),
            "email_subject": self._normalize_text(parsed.get("email_subject", ""))[:80],
            "email_opening_line": self._normalize_text(parsed.get("email_opening_line", ""))[:180],
            "email_draft": self._normalize_text(parsed.get("email_draft", ""))[:900],
            "derived_signals": normalized_signals,
            "cold_call_framework_used": self._normalize_cold_call_framework_used(
                parsed.get("cold_call_framework_used", "permission_problem_binary_soft_close")
            ),
            "cold_call_opening": self._normalize_text(parsed.get("cold_call_opening", ""))[:180],
            "cold_call_problem_hook": self._normalize_text(parsed.get("cold_call_problem_hook", ""))[:300],
            "cold_call_binary_question": self._normalize_text(parsed.get("cold_call_binary_question", ""))[:260],
            "cold_call_soft_close": self._normalize_text(parsed.get("cold_call_soft_close", ""))[:220],
            "cold_call_script": self._normalize_text(parsed.get("cold_call_script", ""))[:1200],
            "contact_name": parsed["contact_name"][:180],
            "contact_role": parsed["contact_role"][:180],
            "contact_name_confidence": self._normalize_confidence_label(
                parsed.get("contact_name_confidence", "low"), "low"
            ),
            "address_text": parsed["address_text"][:300],
            "address_confidence": self._normalize_confidence_label(
                parsed.get("address_confidence", "low"), "low"
            ),
            "contact_evidence_text": self._normalize_contact_evidence_text(
                parsed.get("contact_evidence_text", ""),
                parsed,
            )[:500],
        }