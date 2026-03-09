# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------
# This is a sample controller
# this file is released under public domain and you can use without limitations
# -------------------------------------------------------------------------

# ---- example index page ----


import json, time, uuid, random, hashlib, io
from gluon.http import HTTP
import traceback  # <--- IL MANQUAIT CELUI-CI

GOOGLE_AUTH_URL      = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL     = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL  = 'https://openidconnect.googleapis.com/v1/userinfo'
GOOGLE_SCOPE         = 'openid email profile'


def tableau():
    # Liste toutes les recherches, de la plus récente à la plus ancienne
    runs = db(db.prospect_run.id > 0).select(orderby=~db.prospect_run.id)
    return dict(runs=runs)


def _build_run_execution_dependencies():
    import importlib

    from gluon.contrib.appconfig import AppConfig

    import applications.reasoningframe.modules.application.validators as validators_module
    import applications.reasoningframe.modules.application.run_service as run_service_module
    import applications.reasoningframe.modules.application.prospect_service as prospect_service_module
    import applications.reasoningframe.modules.application.run_execution_service as run_execution_service_module

    import applications.reasoningframe.modules.infrastructure.brave_search_provider as brave_search_provider_module
    import applications.reasoningframe.modules.infrastructure.requests_fetcher as requests_fetcher_module
    import applications.reasoningframe.modules.infrastructure.contact_extractor as contact_extractor_module
    import applications.reasoningframe.modules.infrastructure.gemini_llm_client as gemini_llm_client_module
    import applications.reasoningframe.modules.infrastructure.visible_people_extractor as visible_people_extractor_module

    importlib.reload(validators_module)
    importlib.reload(run_service_module)
    importlib.reload(prospect_service_module)
    importlib.reload(run_execution_service_module)
    importlib.reload(brave_search_provider_module)
    importlib.reload(requests_fetcher_module)
    importlib.reload(contact_extractor_module)
    importlib.reload(gemini_llm_client_module)
    importlib.reload(visible_people_extractor_module)

    SearchRequestValidator = validators_module.SearchRequestValidator
    QualificationCriteriaValidator = validators_module.QualificationCriteriaValidator
    RunWorkflowValidator = validators_module.RunWorkflowValidator

    RunService = run_service_module.RunService
    ProspectService = prospect_service_module.ProspectService
    RunExecutionService = run_execution_service_module.RunExecutionService

    BraveSearchProvider = brave_search_provider_module.BraveSearchProvider
    RequestsWebPageFetcher = requests_fetcher_module.RequestsWebPageFetcher
    RegexContactExtractor = contact_extractor_module.RegexContactExtractor
    GeminiLLMClient = gemini_llm_client_module.GeminiLLMClient
    VisiblePeopleExtractor = visible_people_extractor_module.VisiblePeopleExtractor

    myconf = AppConfig(reload=True)

    run_service = RunService(
        db=db,
        search_request_validator=SearchRequestValidator(),
        criteria_validator=QualificationCriteriaValidator(),
        workflow_validator=RunWorkflowValidator(),
    )

    prospect_service = ProspectService(db=db)

    search_provider = BraveSearchProvider(
        api_key=myconf.get("brave.api_key")
    )

    web_page_fetcher = RequestsWebPageFetcher()
    contact_extractor = RegexContactExtractor()
    visible_people_extractor = VisiblePeopleExtractor()

    llm_client = GeminiLLMClient(
        api_key=myconf.get("gemini.api_key")
    )

    execution_service = RunExecutionService(
        db=db,
        run_service=run_service,
        prospect_service=prospect_service,
        search_provider=search_provider,
        web_page_fetcher=web_page_fetcher,
        contact_extractor=contact_extractor,
        llm_client=llm_client,
        visible_people_extractor=visible_people_extractor,
        default_phone_region="FR",
    )

    return dict(
        run_service=run_service,
        prospect_service=prospect_service,
        execution_service=execution_service,
    )


    
def prospect_run_new():
    deps = _build_run_execution_dependencies()
    run_service = deps["run_service"]

    form = FORM(
        DIV(
            LABEL("Business type / niche"),
            INPUT(_name="niche", _class="form-control", requires=IS_NOT_EMPTY()),
            _class="form-group",
        ),
        DIV(
            LABEL("City / area"),
            INPUT(_name="city", _class="form-control", requires=IS_NOT_EMPTY()),
            _class="form-group",
        ),
        DIV(
            LABEL("What do you sell?"),
            TEXTAREA(_name="offer", _class="form-control", value=""),
            _class="form-group",
        ),
        DIV(
            LABEL("Qualification criteria (optional)"),
            TEXTAREA(
                _name="raw_criteria",
                _class="form-control",
                value="",
                _placeholder="must_mention:booking\nmust_not_mention:klaviyo",
            ),
            _class="form-group",
        ),
        DIV(
            LABEL("Result limit"),
            INPUT(_name="requested_result_limit", _class="form-control", value="10"),
            _class="form-group",
        ),
        DIV(
            INPUT(_type="submit", _value="Create run", _class="btn btn-primary"),
            _class="form-group",
        ),
        _class="outreach-run-form",
    )

    if form.process().accepted:
        try:
            run = run_service.create_run(
                niche=request.vars.niche,
                city=request.vars.city,
                offer=request.vars.offer,
                raw_criteria=request.vars.raw_criteria,
                requested_result_limit=request.vars.requested_result_limit,
            )
            session.flash = "Run created."
            redirect(URL("prospect_run_execute", args=[run.id]))
        except Exception as e:
            response.flash = str(e)

    return dict(form=form)



def prospect_run_execute():
    deps = _build_run_execution_dependencies()
    execution_service = deps["execution_service"]

    run_id = request.args(0, cast=int)
    if not run_id:
        session.flash = "Missing run_id."
        redirect(URL("prospect_run_new"))

    try:
        execution_service.execute_run(run_id)
        session.flash = "Run executed successfully."
    except Exception as e:
        session.flash = "Run execution failed: %s" % e

    redirect(URL("prospect_run_results", args=[run_id]))



def prospect_run_status():
    run_id = request.args(0, cast=int)
    if not run_id:
        return response.json({"ok": False, "error": "missing_run_id"})

    run = db.prospect_run(run_id)
    if not run:
        return response.json({"ok": False, "error": "run_not_found"})

    return response.json({
        "ok": True,
        "id": run.id,
        "run_uuid": run.run_uuid,
        "status": run.status,
        "payment_status": run.payment_status,
        "is_unlocked": run.is_unlocked,
        "preview_count": run.preview_count,
        "discovered_count": run.discovered_count,
        "processed_count": run.processed_count,
        "error_count": run.error_count,
        "last_error_message": run.last_error_message,
    })


def _build_pre_llm_debug_payload(run_row, prospect_row):
    source_pages = db(
        db.prospect_source_page.prospect_id == prospect_row.id
    ).select(orderby=db.prospect_source_page.id)

    contacts = db(
        db.prospect_contact.prospect_id == prospect_row.id
    ).select(orderby=~db.prospect_contact.is_primary | ~db.prospect_contact.confidence)

    signals = db(
        db.prospect_signal.prospect_id == prospect_row.id
    ).select(orderby=db.prospect_signal.id)

    visible_people = []
    if "prospect_visible_person" in db.tables:
        visible_people = db(
            db.prospect_visible_person.prospect_id == prospect_row.id
        ).select(orderby=~db.prospect_visible_person.confidence)

    page_chunks = []
    for page in source_pages:
        text = (page.extracted_text or "").strip()
        if text:
            page_chunks.append(text)

    site_text = "\n\n".join(page_chunks).strip()

    rule_signals_payload = []
    for sig in signals:
        if (sig.source_kind or "") == "rule":
            rule_signals_payload.append({
                "signal_type": sig.signal_type,
                "signal_value": sig.signal_value,
                "polarity": sig.polarity,
                "source_kind": sig.source_kind,
                "confidence": sig.confidence,
                "reason": sig.reason,
            })

    contacts_payload = []
    for c in contacts:
        contacts_payload.append({
            "contact_type": c.contact_type,
            "value": c.value,
            "contact_name": c.contact_name,
            "contact_role": c.contact_role,
            "address_text": c.address_text,
            "evidence_text": c.evidence_text,
            "source_url": c.source_url,
            "confidence": c.confidence,
            "is_primary": c.is_primary,
        })

    visible_people_payload = []
    for p in visible_people:
        visible_people_payload.append({
            "full_name": p.full_name,
            "role_text": p.role_text,
            "source_url": p.source_url,
            "evidence_text": p.evidence_text,
            "confidence": p.confidence,
        })

    business_context = {
        "niche": run_row.niche,
        "city": run_row.city,
        "offer": run_row.offer,
        "output_language": "fr",
        "signals": rule_signals_payload,
    }

    return {
        "business_context": business_context,
        "site_text": site_text,
        "contacts_payload": contacts_payload,
        "visible_people_payload": visible_people_payload,
    }


def prospect_run_results():
    run_id = request.args(0, cast=int)
    if not run_id:
        session.flash = "Missing run_id."
        redirect(URL("prospect_run_new"))

    run = db.prospect_run(run_id)
    if not run:
        session.flash = "Run not found."
        redirect(URL("prospect_run_new"))

    prospects = db(db.prospect.run_id == run.id).select(orderby=db.prospect.render_order)

    rows = []
    for prospect in prospects:
        contacts = db(
            db.prospect_contact.prospect_id == prospect.id
        ).select(orderby=~db.prospect_contact.is_primary | ~db.prospect_contact.confidence)

        signals = db(
            db.prospect_signal.prospect_id == prospect.id
        ).select(orderby=~db.prospect_signal.confidence)

        artifact = db(
            db.prospect_artifact.prospect_id == prospect.id
        ).select().first()

        sources = db(
            db.prospect_source_page.prospect_id == prospect.id
        ).select()

        primary_contact = None
        for c in contacts:
            if c.is_primary:
                primary_contact = c
                break
        if not primary_contact and contacts:
            primary_contact = contacts.first()

        visible_people = []
        if "prospect_visible_person" in db.tables:
            visible_people = db(
                db.prospect_visible_person.prospect_id == prospect.id
            ).select(orderby=~db.prospect_visible_person.confidence)

        pre_llm_debug = _build_pre_llm_debug_payload(run, prospect)

        rows.append(dict(
            prospect=prospect,
            primary_contact=primary_contact,
            contacts=contacts,
            signals=signals,
            artifact=artifact,
            sources=sources,
            visible_people=visible_people,
            pre_llm_debug=pre_llm_debug,
        ))

    if run.is_unlocked:
        visible_rows = rows
        hidden_count = 0
    else:
        visible_rows = rows[:run.preview_count]
        hidden_count = max(0, len(rows) - len(visible_rows))

    return dict(
        run=run,
        rows=rows,
        visible_rows=visible_rows,
        hidden_count=hidden_count,
    )



def prospect_run_results():
    run_id = request.args(0, cast=int)
    if not run_id:
        session.flash = "Missing run_id."
        redirect(URL("prospect_run_new"))

    run = db.prospect_run(run_id)
    if not run:
        session.flash = "Run not found."
        redirect(URL("prospect_run_new"))

    prospects = db(db.prospect.run_id == run.id).select(orderby=db.prospect.render_order)

    rows = []
    for prospect in prospects:
        contacts = db(
            db.prospect_contact.prospect_id == prospect.id
        ).select(orderby=~db.prospect_contact.is_primary | ~db.prospect_contact.confidence)

        signals = db(
            db.prospect_signal.prospect_id == prospect.id
        ).select(orderby=~db.prospect_signal.confidence)

        artifact = db(
            db.prospect_artifact.prospect_id == prospect.id
        ).select().first()

        sources = db(
            db.prospect_source_page.prospect_id == prospect.id
        ).select()

        primary_contact = None
        for c in contacts:
            if c.is_primary:
                primary_contact = c
                break
        if not primary_contact and contacts:
            primary_contact = contacts.first()

        visible_people = db(db.prospect_visible_person.prospect_id == prospect.id).select(orderby=~db.prospect_visible_person.confidence)
        pre_llm_debug = _build_pre_llm_debug_payload(run, prospect)
        rows.append(dict(
        prospect=prospect,
        primary_contact=primary_contact,
        contacts=contacts,
        signals=signals,
        artifact=artifact,
        sources=sources,
        visible_people=visible_people,
        pre_llm_debug=pre_llm_debug,
    ))

    if run.is_unlocked:
        visible_rows = rows
        hidden_count = 0
    else:
        visible_rows = rows[:run.preview_count]
        hidden_count = max(0, len(rows) - len(visible_rows))

    return dict(
        run=run,
        rows=rows,
        visible_rows=visible_rows,
        hidden_count=hidden_count,
    )




def test_gemini_llm_client_v41_bilingual_corpus():
    import json
    import time
    import importlib
    from gluon.contrib.appconfig import AppConfig

    import applications.reasoningframe.modules.infrastructure.gemini_llm_client as gemini_module

    importlib.reload(gemini_module)

    GeminiLLMClient = gemini_module.GeminiLLMClient

    myconf = AppConfig(reload=True)
    api_key = myconf.get("gemini.api_key")

    rows = []

    def add_row(row):
        rows.append(row)

    def normalize_text(value):
        if value is None:
            return ""
        return " ".join(str(value).split()).strip()

    def build_corpus():
        return [
            # --------------------------------------------------
            # ENGLISH
            # --------------------------------------------------
            {
                "case_id": "EN_DESIGN_DENTIST_PARIS",
                "language": "en",
                "label": "Dentist Paris - redesign + conversion",
                "offer_family": "design",
                "expected_fit": ["high"],
                "business_context": {
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
                },
                "site_text": """
                Modern dental clinic in Paris.
                Patients can book appointments online.
                The clinic offers cosmetic dentistry, implants, and emergency dental care.
                Practice Director: Dr. Claire Martin.
                Address: 28 rue Meslay, 75003 Paris, France.
                Contact: contact@clinic-example.com
                """,
            },
            {
                "case_id": "EN_IT_DIGITAL_AGENCY_LYON",
                "language": "en",
                "label": "Digital agency Lyon - white-label subcontracting",
                "offer_family": "sous_traitance_it",
                "expected_fit": ["medium"],
                "business_context": {
                    "niche": "digital agencies",
                    "city": "Lyon",
                    "offer": "white-label software subcontracting for delivery support",
                    "output_language": "en",
                    "signals": [
                        {
                            "signal_type": "multi_service_delivery",
                            "signal_value": "saas ecommerce mobile backend qa support",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.88,
                            "reason": "The site lists multiple technical delivery capabilities."
                        }
                    ],
                },
                "site_text": """
                Digital product agency in Lyon.
                We design and build SaaS platforms, e-commerce sites, mobile apps,
                backend systems, QA workflows, and support projects for clients across Europe.
                """,
            },
            {
                "case_id": "EN_SEO_PLUMBER_MARSEILLE",
                "language": "en",
                "label": "Plumber Marseille - local SEO",
                "offer_family": "seo_local",
                "expected_fit": ["high"],
                "business_context": {
                    "niche": "plumbers",
                    "city": "Marseille",
                    "offer": "local SEO and inbound lead generation",
                    "output_language": "en",
                    "signals": [
                        {
                            "signal_type": "local_service_area_visible",
                            "signal_value": "Marseille Aubagne Cassis",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.90,
                            "reason": "The site mentions several local service areas."
                        },
                        {
                            "signal_type": "lead_capture_visible",
                            "signal_value": "free quote and intervention form",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.91,
                            "reason": "The site displays lead capture entry points."
                        }
                    ],
                },
                "site_text": """
                Plumbing Express Marseille.
                24/7 emergency plumbing, leak detection, drain cleaning, water heater services.
                We serve Marseille, Aubagne, and Cassis.
                Request service through our form.
                Free quote available.
                Phone: 04 91 00 00 00
                """,
            },
            {
                "case_id": "EN_AUTOMATION_REAL_ESTATE_NICE",
                "language": "en",
                "label": "Real estate agency Nice - lead qualification automation",
                "offer_family": "automation",
                "expected_fit": ["high", "medium"],
                "business_context": {
                    "niche": "real estate agencies",
                    "city": "Nice",
                    "offer": "lead qualification automation and commercial follow-up automation",
                    "output_language": "en",
                    "signals": [
                        {
                            "signal_type": "multiple_lead_entrypoints",
                            "signal_value": "seller form buyer form appointment booking",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.93,
                            "reason": "The site exposes multiple lead entry points."
                        }
                    ],
                },
                "site_text": """
                Real estate agency in Nice Centre.
                Free property valuation.
                Seller form, buyer form, and appointment booking.
                Email alerts for new listings.
                Contact: contact@immo-nice.com
                """,
            },
            {
                "case_id": "EN_LOW_FIT_INDUSTRIAL_LILLE",
                "language": "en",
                "label": "Industrial supplier Lille - low fit design",
                "offer_family": "design",
                "expected_fit": ["low"],
                "business_context": {
                    "niche": "service businesses",
                    "city": "Lille",
                    "offer": "brand design and website redesign",
                    "output_language": "en",
                    "signals": [],
                },
                "site_text": """
                Industrial equipment supplier.
                Product catalog, technical references, certifications,
                distributor network information, and documentation.
                """,
            },

            # --------------------------------------------------
            # FRENCH
            # --------------------------------------------------
            {
                "case_id": "FR_DESIGN_DENTISTE_PARIS",
                "language": "fr",
                "label": "Dentiste Paris - refonte + conversion",
                "offer_family": "design",
                "expected_fit": ["high"],
                "business_context": {
                    "niche": "dentistes",
                    "city": "Paris",
                    "offer": "refonte de site web et optimisation de conversion",
                    "output_language": "fr",
                    "signals": [
                        {
                            "signal_type": "booking_detected",
                            "signal_value": "prise de rendez-vous en ligne visible",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.95,
                            "reason": "La prise de rendez-vous en ligne est visible sur le site."
                        }
                    ],
                },
                "site_text": """
                Cabinet dentaire moderne à Paris.
                Les patients peuvent prendre rendez-vous en ligne.
                Le cabinet propose implants, esthétique dentaire et urgences.
                Directrice du cabinet : Dr Claire Martin.
                Adresse : 28 rue Meslay, 75003 Paris, France.
                Contact : contact@clinic-example.fr
                """,
            },
            {
                "case_id": "FR_IT_AGENCE_DIGITALE_LYON",
                "language": "fr",
                "label": "Agence digitale Lyon - sous-traitance IT white-label",
                "offer_family": "sous_traitance_it",
                "expected_fit": ["medium"],
                "business_context": {
                    "niche": "agences digitales",
                    "city": "Lyon",
                    "offer": "sous-traitance logicielle white-label pour absorber la charge projet",
                    "output_language": "fr",
                    "signals": [
                        {
                            "signal_type": "multi_service_delivery",
                            "signal_value": "saas ecommerce mobile backend qa",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.88,
                            "reason": "Le site liste plusieurs types de delivery technique."
                        }
                    ],
                },
                "site_text": """
                Agence digitale à Lyon.
                Nous concevons et développons des plateformes SaaS, des sites e-commerce,
                des applications mobiles, des systèmes backend et des workflows QA
                pour des clients en France et en Europe.
                """,
            },
            {
                "case_id": "FR_SEO_PLOMBIER_MARSEILLE",
                "language": "fr",
                "label": "Plombier Marseille - SEO local / leads entrants",
                "offer_family": "seo_local",
                "expected_fit": ["high"],
                "business_context": {
                    "niche": "plombiers",
                    "city": "Marseille",
                    "offer": "seo local et génération de leads entrants",
                    "output_language": "fr",
                    "signals": [
                        {
                            "signal_type": "local_service_area_visible",
                            "signal_value": "Marseille Aubagne Cassis",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.90,
                            "reason": "Le site mentionne plusieurs zones locales desservies."
                        },
                        {
                            "signal_type": "lead_capture_visible",
                            "signal_value": "devis gratuit et formulaire d'intervention",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.91,
                            "reason": "Le site affiche des points d'entrée de capture de demande."
                        }
                    ],
                },
                "site_text": """
                Plomberie Express Marseille.
                Dépannage 24h/24 et 7j/7, recherche de fuite, débouchage, chauffe-eau.
                Interventions à Marseille, Aubagne, Cassis.
                Demande d'intervention via formulaire.
                Devis gratuit.
                Téléphone : 04 91 00 00 00
                """,
            },
            {
                "case_id": "FR_AUTOMATION_IMMO_NICE",
                "language": "fr",
                "label": "Agence immobilière Nice - automation / qualification leads",
                "offer_family": "automation",
                "expected_fit": ["high", "medium"],
                "business_context": {
                    "niche": "agences immobilières",
                    "city": "Nice",
                    "offer": "automatisation de qualification de leads et suivi commercial",
                    "output_language": "fr",
                    "signals": [
                        {
                            "signal_type": "multiple_lead_entrypoints",
                            "signal_value": "estimation vendeur formulaire acquéreur rendez-vous",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.93,
                            "reason": "Le site expose plusieurs formulaires et points d'entrée de leads."
                        }
                    ],
                },
                "site_text": """
                Agence immobilière Nice Centre.
                Estimation gratuite de votre bien.
                Formulaire vendeur, formulaire acquéreur, prise de rendez-vous.
                Alertes email pour les nouveaux biens.
                Contact : contact@immo-nice.fr
                """,
            },
            {
                "case_id": "FR_LOW_FIT_INDUSTRIEL_LILLE",
                "language": "fr",
                "label": "Fournisseur industriel Lille - faible fit design",
                "offer_family": "design",
                "expected_fit": ["low"],
                "business_context": {
                    "niche": "entreprises de services",
                    "city": "Lille",
                    "offer": "design de marque et refonte de site web",
                    "output_language": "fr",
                    "signals": [],
                },
                "site_text": """
                Fournisseur d'équipements industriels.
                Catalogue produits, fiches techniques, certifications,
                réseau de distributeurs et documentation.
                """,
            },
        ]

    def validate_common_payload(payload):
        required_keys = [
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
            "llm_model_used",
        ]

        missing = [k for k in required_keys if k not in payload]
        if missing:
            raise Exception("Missing keys: %s" % missing)

        if payload["fit_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid fit_confidence: %s" % payload["fit_confidence"])

        if payload["contact_name_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid contact_name_confidence: %s" % payload["contact_name_confidence"])

        if payload["address_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid address_confidence: %s" % payload["address_confidence"])

        if payload["email_framework_used"] != "reply_first_micro_pas":
            raise Exception("Invalid email_framework_used: %s" % payload["email_framework_used"])

        if payload["cold_call_framework_used"] != "permission_problem_binary_soft_close":
            raise Exception("Invalid cold_call_framework_used: %s" % payload["cold_call_framework_used"])

        if not isinstance(payload["derived_signals"], list):
            raise Exception("derived_signals must be a list")

        if len(payload["derived_signals"]) > 3:
            raise Exception("derived_signals must contain at most 3 items")

        for i, sig in enumerate(payload["derived_signals"]):
            if sig.get("polarity") not in ("positive", "negative", "unknown"):
                raise Exception("Invalid polarity in derived_signals[%s]" % i)

            if sig.get("source_kind") != "llm":
                raise Exception("source_kind must be 'llm' in derived_signals[%s]" % i)

            confidence = sig.get("confidence")
            if not isinstance(confidence, (int, float)):
                raise Exception("confidence must be numeric in derived_signals[%s]" % i)

            if confidence < 0.0 or confidence > 1.0:
                raise Exception("confidence out of range in derived_signals[%s]" % i)

        return True

    def collect_language_sensitive_text(payload):
        chunks = [
            payload.get("business_summary", ""),
            payload.get("qualification_explanation", ""),
            payload.get("llm_business_type", ""),
            payload.get("llm_offer_fit", ""),
            payload.get("outreach_angle", ""),
            payload.get("email_subject", ""),
            payload.get("email_opening_line", ""),
            payload.get("email_draft", ""),
            payload.get("cold_call_opening", ""),
            payload.get("cold_call_problem_hook", ""),
            payload.get("cold_call_binary_question", ""),
            payload.get("cold_call_soft_close", ""),
            payload.get("cold_call_script", ""),
            payload.get("contact_name", ""),
            payload.get("contact_role", ""),
            payload.get("address_text", ""),
            payload.get("contact_evidence_text", ""),
        ]

        for sig in payload.get("derived_signals", []):
            if isinstance(sig, dict):
                chunks.append(sig.get("signal_type", ""))
                chunks.append(sig.get("signal_value", ""))
                chunks.append(sig.get("reason", ""))

        return " ".join([normalize_text(x) for x in chunks if normalize_text(x)])

    def french_like(text):
        text = " " + normalize_text(text).lower() + " "
        markers = [
            " le ", " la ", " les ", " de ", " des ", " du ", " un ", " une ",
            " pour ", " votre ", " vous ", " sur ", " avec ", " est ", " au ",
            " aux ", " dans ", " que ", " qui ", " plus ", " peut ", " cela ",
            " rendez-vous ", " devis ", " agence ", " cabinet ", " entreprise ",
            " rapide ", " formulaire ", " priorité ", " clients ", " pertinence "
        ]
        hits = 0
        for m in markers:
            if m in text:
                hits += 1

        obvious_english = [
            " quick look ",
            " next week ",
            " worth sending ",
            " open to ",
            " booking flow question ",
            " delivery capacity question ",
            " multiple forms and appointment requests ",
            " online booking flow ",
        ]
        if any(bad in text for bad in obvious_english):
            return False

        return hits >= 4

    def english_like(text):
        text = " " + normalize_text(text).lower() + " "
        markers = [
            " the ", " and ", " for ", " with ", " this ", " that ", " your ",
            " you ", " open to ", " quick ", " question ", " booking ", " traffic ",
            " lead ", " call ", " business ", " relevant ", " delivery ", " support "
        ]
        hits = 0
        for m in markers:
            if m in text:
                hits += 1

        obvious_french = [
            " le ", " la ", " les ", " de ", " des ", " du ", " rendez-vous ",
            " devis ", " entreprise ", " agence ", " cabinet ", " rapide ",
            " serait-il ", " pourriez-vous ", " en discuter ", " semaine prochaine "
        ]
        if any(bad in text for bad in obvious_french):
            return False

        return hits >= 4

    def contact_rule_ok(payload):
        has_contact = bool(
            normalize_text(payload.get("contact_name", "")) or
            normalize_text(payload.get("contact_role", "")) or
            normalize_text(payload.get("address_text", ""))
        )
        if has_contact:
            return bool(normalize_text(payload.get("contact_evidence_text", "")))
        return True

    def has_duplicate_derived_signals(payload, input_signals):
        input_keys = set()
        for sig in input_signals or []:
            if isinstance(sig, dict):
                input_keys.add((
                    normalize_text(sig.get("signal_type", "")).lower(),
                    normalize_text(sig.get("signal_value", "")).lower(),
                ))

        for sig in payload.get("derived_signals", []):
            key = (
                normalize_text(sig.get("signal_type", "")).lower(),
                normalize_text(sig.get("signal_value", "")).lower(),
            )
            if key in input_keys:
                return True
        return False

    def contains_hard_cta(text):
        text = normalize_text(text).lower()
        banned = [
            "book a demo",
            "schedule a demo",
            "30-minute demo",
            "30 minute demo",
            "buy now",
            "sign up now",
            "start your free trial",
            "book a call now",
            "schedule a call now",
            "réservez une démo",
            "réserver une démo",
            "planifiez une démo",
            "planifier une démo",
            "achetez maintenant",
            "réservez un appel",
            "réserver un appel",
            "planifiez un appel",
            "planifier un appel",
        ]
        for phrase in banned:
            if phrase in text:
                return True
        return False

    def contains_link(text):
        text = normalize_text(text).lower()
        return ("http://" in text) or ("https://" in text) or ("www." in text)

    def email_sendable(payload):
        subject = normalize_text(payload.get("email_subject", ""))
        opening = normalize_text(payload.get("email_opening_line", ""))
        draft = normalize_text(payload.get("email_draft", ""))

        if not subject or not opening or not draft:
            return False

        if contains_hard_cta(subject + " " + opening + " " + draft):
            return False

        if contains_link(draft):
            return False

        banned_fluff = [
            "j'espère que vous allez bien",
            "i hope this email finds you well",
            "we help businesses like yours grow",
            "nous aidons les entreprises comme la vôtre à croître",
        ]
        text = (subject + " " + opening + " " + draft).lower()
        for phrase in banned_fluff:
            if phrase in text:
                return False

        return True

    def call_sendable(payload):
        script = normalize_text(payload.get("cold_call_script", ""))
        if not script:
            return False
        if contains_hard_cta(script):
            return False
        return True

    def low_fit_prudent(payload):
        if payload.get("fit_confidence") != "low":
            return True

        combined = " ".join([
            payload.get("email_subject", ""),
            payload.get("email_opening_line", ""),
            payload.get("email_draft", ""),
            payload.get("cold_call_opening", ""),
            payload.get("cold_call_problem_hook", ""),
            payload.get("cold_call_binary_question", ""),
            payload.get("cold_call_soft_close", ""),
            payload.get("cold_call_script", ""),
        ])

        if contains_hard_cta(combined):
            return False

        if contains_link(payload.get("email_draft", "")):
            return False

        return True

    def score_case(payload, case):
        score = 0
        flags = {}

        # Structure
        try:
            validate_common_payload(payload)
            flags["structure_ok"] = True
            score += 20
        except Exception:
            flags["structure_ok"] = False

        # Fit
        flags["fit_match"] = payload.get("fit_confidence") in case["expected_fit"]
        if flags["fit_match"]:
            score += 15

        # Language
        lang_text = collect_language_sensitive_text(payload)
        if case["language"] == "fr":
            flags["language_ok"] = french_like(lang_text)
        else:
            flags["language_ok"] = english_like(lang_text)
        if flags["language_ok"]:
            score += 15

        # Contact rule
        flags["contact_rule_ok"] = contact_rule_ok(payload)
        if flags["contact_rule_ok"]:
            score += 10

        # Derived signals
        flags["derived_signals_ok"] = not has_duplicate_derived_signals(
            payload,
            case["business_context"].get("signals", [])
        )
        if flags["derived_signals_ok"]:
            score += 10

        # Prudence
        flags["low_fit_prudent_ok"] = low_fit_prudent(payload)
        if flags["low_fit_prudent_ok"]:
            score += 10

        # Email
        flags["email_sendable_ok"] = email_sendable(payload)
        if flags["email_sendable_ok"]:
            score += 10

        # Call
        flags["call_sendable_ok"] = call_sendable(payload)
        if flags["call_sendable_ok"]:
            score += 10

        return score, flags

    def build_summary(rows):
        total = len(rows)
        passed = len([r for r in rows if r["status"] == "PASS"])
        failed = total - passed

        success_rows = [r for r in rows if r["status"] == "PASS"]

        avg_score = 0.0
        if success_rows:
            avg_score = round(sum(r["score"] for r in success_rows) / float(len(success_rows)), 2)

        fit_distribution = {"low": 0, "medium": 0, "high": 0}
        for r in success_rows:
            fit = r.get("actual_fit", "")
            if fit in fit_distribution:
                fit_distribution[fit] += 1

        def rate(flag_name, language=None):
            subset = success_rows
            if language:
                subset = [r for r in subset if r.get("language") == language]
            if not subset:
                return 0.0
            ok_count = len([r for r in subset if r.get("flags", {}).get(flag_name) is True])
            return round((ok_count * 100.0) / float(len(subset)), 2)

        def avg_score_for(language):
            subset = [r for r in success_rows if r.get("language") == language]
            if not subset:
                return 0.0
            return round(sum(r["score"] for r in subset) / float(len(subset)), 2)

        by_language = {}
        for lang in ["en", "fr"]:
            subset = [r for r in rows if r.get("language") == lang]
            by_language[lang] = {
                "total": len(subset),
                "passed": len([r for r in subset if r["status"] == "PASS"]),
                "failed": len([r for r in subset if r["status"] == "FAIL"]),
                "avg_score": avg_score_for(lang),
                "fit_match_rate": rate("fit_match", lang),
                "language_rate": rate("language_ok", lang),
                "email_sendable_rate": rate("email_sendable_ok", lang),
                "call_sendable_rate": rate("call_sendable_ok", lang),
                "contact_rule_rate": rate("contact_rule_ok", lang),
                "derived_signals_rate": rate("derived_signals_ok", lang),
                "low_fit_prudence_rate": rate("low_fit_prudent_ok", lang),
            }

        return {
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": failed,
            "average_score": avg_score,
            "fit_distribution": fit_distribution,
            "overall_fit_match_rate": rate("fit_match"),
            "overall_language_rate": rate("language_ok"),
            "overall_email_sendable_rate": rate("email_sendable_ok"),
            "overall_call_sendable_rate": rate("call_sendable_ok"),
            "overall_contact_rule_rate": rate("contact_rule_ok"),
            "overall_derived_signals_rate": rate("derived_signals_ok"),
            "overall_low_fit_prudence_rate": rate("low_fit_prudent_ok"),
            "by_language": by_language,
        }

    if not api_key:
        add_row({
            "case_id": "API_KEY",
            "language": "system",
            "label": "Gemini API key presence",
            "offer_family": "system",
            "expected_fit": [],
            "actual_fit": "",
            "status": "FAIL",
            "score": 0,
            "flags": {},
            "duration_sec": 0,
            "error": "Missing [gemini] api_key in private/appconfig.ini",
            "payload": None,
        })
        return dict(summary=build_summary(rows), rows=rows, json=json)

    try:
        client = GeminiLLMClient(api_key=api_key)
    except Exception as e:
        add_row({
            "case_id": "CLIENT_INIT",
            "language": "system",
            "label": "Gemini client init",
            "offer_family": "system",
            "expected_fit": [],
            "actual_fit": "",
            "status": "FAIL",
            "score": 0,
            "flags": {},
            "duration_sec": 0,
            "error": str(e),
            "payload": None,
        })
        return dict(summary=build_summary(rows), rows=rows, json=json)

    corpus = build_corpus()

    for case in corpus:
        started = time.time()
        try:
            payload = client.enrich_prospect(
                site_text=case["site_text"],
                business_context=case["business_context"],
            )

            validate_common_payload(payload)
            score, flags = score_case(payload, case)

            add_row({
                "case_id": case["case_id"],
                "language": case["language"],
                "label": case["label"],
                "offer_family": case["offer_family"],
                "expected_fit": case["expected_fit"],
                "actual_fit": payload.get("fit_confidence", ""),
                "status": "PASS",
                "score": score,
                "flags": flags,
                "duration_sec": round(time.time() - started, 2),
                "error": "",
                "payload": payload,
            })

        except Exception as e:
            add_row({
                "case_id": case["case_id"],
                "language": case["language"],
                "label": case["label"],
                "offer_family": case["offer_family"],
                "expected_fit": case["expected_fit"],
                "actual_fit": "",
                "status": "FAIL",
                "score": 0,
                "flags": {},
                "duration_sec": round(time.time() - started, 2),
                "error": str(e),
                "payload": None,
            })

    summary = build_summary(rows)
    return dict(summary=summary, rows=rows, json=json)



def test_gemini_llm_client_v41_french_corpus():
    import json
    import time
    import importlib
    from gluon.contrib.appconfig import AppConfig

    import applications.reasoningframe.modules.infrastructure.gemini_llm_client as gemini_module

    importlib.reload(gemini_module)

    GeminiLLMClient = gemini_module.GeminiLLMClient

    myconf = AppConfig(reload=True)
    api_key = myconf.get("gemini.api_key")

    results = []

    def add_result(row):
        results.append(row)

    def build_corpus():
        return [
            {
                "case_id": "FR_DESIGN_DENTISTE_PARIS",
                "label": "Dentiste Paris - refonte + conversion",
                "offer_family": "design",
                "expected_fit": ["high"],
                "business_context": {
                    "niche": "dentistes",
                    "city": "Paris",
                    "offer": "refonte de site web et optimisation de conversion",
                    "output_language": "fr",
                    "signals": [
                        {
                            "signal_type": "booking_detected",
                            "signal_value": "prise de rendez-vous en ligne visible",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.95,
                            "reason": "La prise de rendez-vous en ligne est visible sur le site."
                        }
                    ],
                },
                "site_text": """
                Cabinet dentaire moderne à Paris.
                Les patients peuvent prendre rendez-vous en ligne.
                Le cabinet propose implants, esthétique dentaire et urgences.
                Directrice du cabinet : Dr Claire Martin.
                Adresse : 28 rue Meslay, 75003 Paris, France.
                Contact : contact@clinic-example.fr
                """,
            },
            {
                "case_id": "FR_DESIGN_CENTRE_ESTHETIQUE_TOULOUSE",
                "label": "Centre esthétique Toulouse - design / conversion",
                "offer_family": "design",
                "expected_fit": ["high", "medium"],
                "business_context": {
                    "niche": "centres esthétiques",
                    "city": "Toulouse",
                    "offer": "design de marque et refonte de site avec amélioration de conversion",
                    "output_language": "fr",
                    "signals": [
                        {
                            "signal_type": "booking_detected",
                            "signal_value": "réservation en ligne visible",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.92,
                            "reason": "La réservation en ligne est visible sur le site."
                        }
                    ],
                },
                "site_text": """
                Centre esthétique à Toulouse.
                Réservation en ligne disponible.
                Soins visage, épilation laser, soins anti-âge.
                Responsable du centre : Dr Sophie Bernard.
                Adresse : 14 allées Jean Jaurès, 31000 Toulouse.
                Téléphone : 05 61 00 00 00
                """,
            },
            {
                "case_id": "FR_IT_AGENCE_DIGITALE_LYON",
                "label": "Agence digitale Lyon - sous-traitance IT white-label",
                "offer_family": "sous_traitance_it",
                "expected_fit": ["medium"],
                "business_context": {
                    "niche": "agences digitales",
                    "city": "Lyon",
                    "offer": "sous-traitance logicielle white-label pour absorber la charge projet",
                    "output_language": "fr",
                    "signals": [
                        {
                            "signal_type": "multi_service_delivery",
                            "signal_value": "saas ecommerce mobile backend qa",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.88,
                            "reason": "Le site liste plusieurs types de delivery technique."
                        }
                    ],
                },
                "site_text": """
                Agence digitale à Lyon.
                Nous concevons et développons des plateformes SaaS, des sites e-commerce,
                des applications mobiles, des systèmes backend et des workflows QA
                pour des clients en France et en Europe.
                """,
            },
            {
                "case_id": "FR_SEO_PLOMBIER_MARSEILLE",
                "label": "Plombier Marseille - SEO local / leads entrants",
                "offer_family": "seo_local",
                "expected_fit": ["high"],
                "business_context": {
                    "niche": "plombiers",
                    "city": "Marseille",
                    "offer": "seo local et génération de leads entrants",
                    "output_language": "fr",
                    "signals": [
                        {
                            "signal_type": "local_service_area_visible",
                            "signal_value": "Marseille Aubagne Cassis",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.90,
                            "reason": "Le site mentionne plusieurs zones locales desservies."
                        },
                        {
                            "signal_type": "lead_capture_visible",
                            "signal_value": "devis gratuit et formulaire d'intervention",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.91,
                            "reason": "Le site affiche des points d'entrée de capture de demande."
                        }
                    ],
                },
                "site_text": """
                Plomberie Express Marseille.
                Dépannage 24h/24 et 7j/7, recherche de fuite, débouchage, chauffe-eau.
                Interventions à Marseille, Aubagne, Cassis.
                Demande d'intervention via formulaire.
                Devis gratuit.
                Téléphone : 04 91 00 00 00
                """,
            },
            {
                "case_id": "FR_AUTOMATION_IMMO_NICE",
                "label": "Agence immobilière Nice - automation / qualification leads",
                "offer_family": "automation",
                "expected_fit": ["high", "medium"],
                "business_context": {
                    "niche": "agences immobilières",
                    "city": "Nice",
                    "offer": "automatisation de qualification de leads et suivi commercial",
                    "output_language": "fr",
                    "signals": [
                        {
                            "signal_type": "multiple_lead_entrypoints",
                            "signal_value": "estimation vendeur formulaire acquéreur rendez-vous",
                            "polarity": "positive",
                            "source_kind": "rule",
                            "confidence": 0.93,
                            "reason": "Le site expose plusieurs formulaires et points d'entrée de leads."
                        }
                    ],
                },
                "site_text": """
                Agence immobilière Nice Centre.
                Estimation gratuite de votre bien.
                Formulaire vendeur, formulaire acquéreur, prise de rendez-vous.
                Alertes email pour les nouveaux biens.
                Contact : contact@immo-nice.fr
                """,
            },
            {
                "case_id": "FR_LOW_FIT_INDUSTRIEL_LILLE",
                "label": "Fournisseur industriel Lille - faible fit design",
                "offer_family": "design",
                "expected_fit": ["low"],
                "business_context": {
                    "niche": "entreprises de services",
                    "city": "Lille",
                    "offer": "design de marque et refonte de site web",
                    "output_language": "fr",
                    "signals": [],
                },
                "site_text": """
                Fournisseur d'équipements industriels.
                Catalogue produits, fiches techniques, certifications,
                réseau de distributeurs et documentation.
                """,
            },
        ]

    def normalize_text(value):
        if value is None:
            return ""
        value = str(value)
        return " ".join(value.split()).strip()

    def validate_common_payload(payload):
        required_keys = [
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
            "llm_model_used",
        ]

        missing = [k for k in required_keys if k not in payload]
        if missing:
            raise Exception("Missing keys: %s" % missing)

        if payload["fit_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid fit_confidence: %s" % payload["fit_confidence"])

        if payload["contact_name_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid contact_name_confidence: %s" % payload["contact_name_confidence"])

        if payload["address_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid address_confidence: %s" % payload["address_confidence"])

        if payload["email_framework_used"] != "reply_first_micro_pas":
            raise Exception("Invalid email_framework_used: %s" % payload["email_framework_used"])

        if payload["cold_call_framework_used"] != "permission_problem_binary_soft_close":
            raise Exception("Invalid cold_call_framework_used: %s" % payload["cold_call_framework_used"])

        if not isinstance(payload["derived_signals"], list):
            raise Exception("derived_signals must be a list")

        if len(payload["derived_signals"]) > 3:
            raise Exception("derived_signals must contain at most 3 items")

        for i, sig in enumerate(payload["derived_signals"]):
            if sig.get("polarity") not in ("positive", "negative", "unknown"):
                raise Exception("Invalid polarity in derived_signals[%s]" % i)

            if sig.get("source_kind") != "llm":
                raise Exception("source_kind must be 'llm' in derived_signals[%s]" % i)

            confidence = sig.get("confidence")
            if not isinstance(confidence, (int, float)):
                raise Exception("confidence must be numeric in derived_signals[%s]" % i)

            if confidence < 0.0 or confidence > 1.0:
                raise Exception("confidence out of range in derived_signals[%s]" % i)

        return True

    def has_contact_fields(payload):
        return bool(
            normalize_text(payload.get("contact_name", "")) or
            normalize_text(payload.get("contact_role", "")) or
            normalize_text(payload.get("address_text", ""))
        )

    def contact_rule_ok(payload):
        if has_contact_fields(payload):
            return bool(normalize_text(payload.get("contact_evidence_text", "")))
        return True

    def has_duplicate_derived_signals(payload, input_signals):
        input_keys = set()
        for sig in input_signals or []:
            if isinstance(sig, dict):
                input_keys.add((
                    normalize_text(sig.get("signal_type", "")).lower(),
                    normalize_text(sig.get("signal_value", "")).lower(),
                ))

        for sig in payload.get("derived_signals", []):
            key = (
                normalize_text(sig.get("signal_type", "")).lower(),
                normalize_text(sig.get("signal_value", "")).lower(),
            )
            if key in input_keys:
                return True
        return False

    def contains_hard_cta(text):
        text = normalize_text(text).lower()
        banned = [
            "book a demo",
            "schedule a demo",
            "30-minute demo",
            "30 minute demo",
            "buy now",
            "sign up now",
            "start your free trial",
            "book a call now",
            "schedule a call now",
            "réservez une démo",
            "réserver une démo",
            "planifiez une démo",
            "planifier une démo",
            "achetez maintenant",
            "achetez tout de suite",
            "réservez un appel",
            "réserver un appel",
            "planifiez un appel",
            "planifier un appel",
        ]
        for phrase in banned:
            if phrase in text:
                return True
        return False

    def contains_link(text):
        text = normalize_text(text).lower()
        return ("http://" in text) or ("https://" in text) or ("www." in text)

    def french_like(text):
        text = " " + normalize_text(text).lower() + " "
        markers = [
            " le ", " la ", " les ", " de ", " des ", " du ", " un ", " une ",
            " pour ", " votre ", " vous ", " sur ", " avec ", " est ", " au ",
            " aux ", " dans ", " que ", " qui ", " plus ", " peut ", " cela ",
            " rapide ", " regard ", " exemple ", " rendez-vous ", " devis "
        ]
        hits = 0
        for m in markers:
            if m in text:
                hits += 1

        obvious_english = [
            " quick look ",
            " next week ",
            " worth sending ",
            " open to ",
            " booking flow question ",
            " delivery capacity question ",
        ]
        if any(bad in text for bad in obvious_english):
            return False

        return hits >= 3

    def email_sendable(payload):
        subject = normalize_text(payload.get("email_subject", ""))
        draft = normalize_text(payload.get("email_draft", ""))
        opening = normalize_text(payload.get("email_opening_line", ""))

        if not subject or not draft or not opening:
            return False

        if contains_hard_cta(subject + " " + opening + " " + draft):
            return False

        if contains_link(draft):
            return False

        banned_fluff = [
            "j'espère que vous allez bien",
            "i hope this email finds you well",
            "nous aidons les entreprises comme la vôtre à croître",
        ]
        text = (subject + " " + opening + " " + draft).lower()
        for phrase in banned_fluff:
            if phrase in text:
                return False

        if len(draft) > 900:
            return False

        return True

    def call_sendable(payload):
        opening = normalize_text(payload.get("cold_call_opening", ""))
        hook = normalize_text(payload.get("cold_call_problem_hook", ""))
        question = normalize_text(payload.get("cold_call_binary_question", ""))
        close = normalize_text(payload.get("cold_call_soft_close", ""))
        script = normalize_text(payload.get("cold_call_script", ""))

        if not opening or not hook or not question or not close or not script:
            return False

        if contains_hard_cta(script):
            return False

        if len(script) > 1200:
            return False

        return True

    def low_fit_prudent(payload):
        if payload.get("fit_confidence") != "low":
            return True

        combined = " ".join([
            payload.get("email_subject", ""),
            payload.get("email_opening_line", ""),
            payload.get("email_draft", ""),
            payload.get("cold_call_opening", ""),
            payload.get("cold_call_problem_hook", ""),
            payload.get("cold_call_binary_question", ""),
            payload.get("cold_call_soft_close", ""),
            payload.get("cold_call_script", ""),
        ])

        if contains_hard_cta(combined):
            return False

        if contains_link(payload.get("email_draft", "")):
            return False

        return True

    def score_case(payload, case):
        score = 0
        flags = {}

        # 1. Structure / intégrité
        try:
            validate_common_payload(payload)
            flags["structure_ok"] = True
            score += 20
        except Exception:
            flags["structure_ok"] = False

        # 2. Fit attendu
        flags["fit_match"] = payload.get("fit_confidence") in case["expected_fit"]
        if flags["fit_match"]:
            score += 15

        # 3. Français
        combined_lang_text = " ".join([
            payload.get("business_summary", ""),
            payload.get("qualification_explanation", ""),
            payload.get("email_opening_line", ""),
            payload.get("email_draft", ""),
            payload.get("cold_call_opening", ""),
            payload.get("cold_call_problem_hook", ""),
            payload.get("cold_call_script", ""),
        ])
        flags["french_output_ok"] = french_like(combined_lang_text)
        if flags["french_output_ok"]:
            score += 15

        # 4. Contact + preuve
        flags["contact_rule_ok"] = contact_rule_ok(payload)
        if flags["contact_rule_ok"]:
            score += 10

        # 5. Signaux dérivés
        flags["derived_signals_ok"] = not has_duplicate_derived_signals(
            payload,
            case["business_context"].get("signals", [])
        )
        if flags["derived_signals_ok"]:
            score += 10

        # 6. Low fit prudent
        flags["low_fit_prudent_ok"] = low_fit_prudent(payload)
        if flags["low_fit_prudent_ok"]:
            score += 10

        # 7. Email envoyable
        flags["email_sendable_ok"] = email_sendable(payload)
        if flags["email_sendable_ok"]:
            score += 10

        # 8. Call exploitable
        flags["call_sendable_ok"] = call_sendable(payload)
        if flags["call_sendable_ok"]:
            score += 10

        return score, flags

    def build_summary(rows):
        total = len(rows)
        passed = len([r for r in rows if r["status"] == "PASS"])
        failed = total - passed

        successful_rows = [r for r in rows if r["status"] == "PASS"]
        avg_score = 0.0
        if successful_rows:
            avg_score = round(
                sum(r["score"] for r in successful_rows) / float(len(successful_rows)),
                2
            )

        fit_distribution = {"low": 0, "medium": 0, "high": 0}
        for r in successful_rows:
            fit = r.get("actual_fit", "")
            if fit in fit_distribution:
                fit_distribution[fit] += 1

        def rate(flag_name):
            if not successful_rows:
                return 0.0
            ok_count = len([r for r in successful_rows if r.get("flags", {}).get(flag_name) is True])
            return round((ok_count * 100.0) / float(len(successful_rows)), 2)

        by_offer = {}
        for r in rows:
            family = r.get("offer_family", "unknown")
            if family not in by_offer:
                by_offer[family] = {
                    "total": 0,
                    "passed": 0,
                    "avg_score": 0.0,
                    "scores": [],
                }

            by_offer[family]["total"] += 1
            if r["status"] == "PASS":
                by_offer[family]["passed"] += 1
                by_offer[family]["scores"].append(r["score"])

        for family in by_offer:
            scores = by_offer[family]["scores"]
            if scores:
                by_offer[family]["avg_score"] = round(sum(scores) / float(len(scores)), 2)
            del by_offer[family]["scores"]

        return {
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": failed,
            "average_score": avg_score,
            "fit_distribution": fit_distribution,
            "fit_match_rate": rate("fit_match"),
            "french_output_rate": rate("french_output_ok"),
            "contact_rule_rate": rate("contact_rule_ok"),
            "derived_signals_rate": rate("derived_signals_ok"),
            "low_fit_prudence_rate": rate("low_fit_prudent_ok"),
            "sendable_email_rate": rate("email_sendable_ok"),
            "sendable_call_rate": rate("call_sendable_ok"),
            "by_offer_family": by_offer,
        }

    if not api_key:
        add_result({
            "case_id": "API_KEY",
            "label": "Gemini API key presence",
            "offer_family": "system",
            "expected_fit": [],
            "actual_fit": "",
            "status": "FAIL",
            "score": 0,
            "flags": {},
            "duration_sec": 0,
            "error": "Missing [gemini] api_key in private/appconfig.ini",
            "payload": None,
        })
        return dict(summary=build_summary(results), rows=results, json=json)

    try:
        client = GeminiLLMClient(api_key=api_key)
    except Exception as e:
        add_result({
            "case_id": "CLIENT_INIT",
            "label": "Gemini client init",
            "offer_family": "system",
            "expected_fit": [],
            "actual_fit": "",
            "status": "FAIL",
            "score": 0,
            "flags": {},
            "duration_sec": 0,
            "error": str(e),
            "payload": None,
        })
        return dict(summary=build_summary(results), rows=results, json=json)

    corpus = build_corpus()

    for case in corpus:
        started = time.time()
        try:
            payload = client.enrich_prospect(
                site_text=case["site_text"],
                business_context=case["business_context"],
            )

            validate_common_payload(payload)
            score, flags = score_case(payload, case)

            add_result({
                "case_id": case["case_id"],
                "label": case["label"],
                "offer_family": case["offer_family"],
                "expected_fit": case["expected_fit"],
                "actual_fit": payload.get("fit_confidence", ""),
                "status": "PASS",
                "score": score,
                "flags": flags,
                "duration_sec": round(time.time() - started, 2),
                "error": "",
                "payload": payload,
            })

        except Exception as e:
            add_result({
                "case_id": case["case_id"],
                "label": case["label"],
                "offer_family": case["offer_family"],
                "expected_fit": case["expected_fit"],
                "actual_fit": "",
                "status": "FAIL",
                "score": 0,
                "flags": {},
                "duration_sec": round(time.time() - started, 2),
                "error": str(e),
                "payload": None,
            })

    summary = build_summary(results)
    return dict(summary=summary, rows=results, json=json)








def test_gemini_llm_client_v41_business_rules():
    import importlib
    import copy
    from gluon.contrib.appconfig import AppConfig

    import applications.reasoningframe.modules.infrastructure.gemini_llm_client as gemini_module

    importlib.reload(gemini_module)

    GeminiLLMClient = gemini_module.GeminiLLMClient
    GeminiLLMClientError = gemini_module.GeminiLLMClientError

    myconf = AppConfig(reload=True)
    api_key = myconf.get("gemini.api_key")

    results = []

    def add_result(test_name, status, details):
        results.append({
            "test": test_name,
            "status": status,
            "details": details,
        })

    def ensure_common_payload_integrity(payload):
        required_keys = [
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
            "llm_model_used",
        ]

        missing = [k for k in required_keys if k not in payload]
        if missing:
            raise Exception("Missing keys: %s" % missing)

        if payload["fit_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid fit_confidence: %s" % payload["fit_confidence"])

        if payload["contact_name_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid contact_name_confidence: %s" % payload["contact_name_confidence"])

        if payload["address_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid address_confidence: %s" % payload["address_confidence"])

        if payload["email_framework_used"] != "reply_first_micro_pas":
            raise Exception("Invalid email_framework_used: %s" % payload["email_framework_used"])

        if payload["cold_call_framework_used"] != "permission_problem_binary_soft_close":
            raise Exception("Invalid cold_call_framework_used: %s" % payload["cold_call_framework_used"])

        if not isinstance(payload["derived_signals"], list):
            raise Exception("derived_signals must be a list")

        if len(payload["derived_signals"]) > 3:
            raise Exception("derived_signals must contain at most 3 items")

        for i, sig in enumerate(payload["derived_signals"]):
            if sig.get("polarity") not in ("positive", "negative", "unknown"):
                raise Exception("Invalid polarity in derived_signals[%s]" % i)

            if sig.get("source_kind") != "llm":
                raise Exception("source_kind must be 'llm' in derived_signals[%s]" % i)

            confidence = sig.get("confidence")
            if not isinstance(confidence, (int, float)):
                raise Exception("confidence must be numeric in derived_signals[%s]" % i)

            if confidence < 0.0 or confidence > 1.0:
                raise Exception("confidence out of range in derived_signals[%s]" % i)

        return True

    def validate_business_rules(payload, input_signals=None):
        input_signals = input_signals or []
        ensure_common_payload_integrity(payload)

        # --------------------------------------------------
        # 1. Contact evidence rule
        # --------------------------------------------------
        has_contact_fields = bool(
            (payload.get("contact_name") or "").strip() or
            (payload.get("contact_role") or "").strip() or
            (payload.get("address_text") or "").strip()
        )
        if has_contact_fields and not (payload.get("contact_evidence_text") or "").strip():
            raise Exception("Business rule violation: contact fields present without contact_evidence_text")

        # --------------------------------------------------
        # 2. No duplicate derived signals vs input signals
        # --------------------------------------------------
        input_keys = set()
        for sig in input_signals:
            if isinstance(sig, dict):
                input_keys.add((
                    str(sig.get("signal_type", "")).strip().lower(),
                    str(sig.get("signal_value", "")).strip().lower(),
                ))

        for i, sig in enumerate(payload.get("derived_signals", [])):
            key = (
                str(sig.get("signal_type", "")).strip().lower(),
                str(sig.get("signal_value", "")).strip().lower(),
            )
            if key in input_keys:
                raise Exception(
                    "Business rule violation: derived_signals[%s] duplicates an input signal: %s"
                    % (i, key)
                )

        # --------------------------------------------------
        # 3. Low fit must stay conservative
        # --------------------------------------------------
        if payload.get("fit_confidence") == "low":
            combined_email = " ".join([
                payload.get("email_subject", ""),
                payload.get("email_opening_line", ""),
                payload.get("email_draft", ""),
            ]).lower()

            combined_call = " ".join([
                payload.get("cold_call_opening", ""),
                payload.get("cold_call_problem_hook", ""),
                payload.get("cold_call_binary_question", ""),
                payload.get("cold_call_soft_close", ""),
                payload.get("cold_call_script", ""),
            ]).lower()

            banned_hard_cta_phrases = [
                "book a demo",
                "schedule a demo",
                "30-minute demo",
                "buy now",
                "sign up now",
                "start your free trial",
                "jump on a 30-minute call",
                "let's book a call",
                "book a call now",
                "schedule a call now",
            ]

            for phrase in banned_hard_cta_phrases:
                if phrase in combined_email:
                    raise Exception("Business rule violation: low-fit email contains hard CTA phrase: %s" % phrase)
                if phrase in combined_call:
                    raise Exception("Business rule violation: low-fit cold call contains hard CTA phrase: %s" % phrase)

            if "http://" in combined_email or "https://" in combined_email:
                raise Exception("Business rule violation: low-fit first email should not contain links")

        return True

    # --------------------------------------------------
    # 0. API key presence
    # --------------------------------------------------
    if not api_key:
        add_result(
            "Gemini API key presence",
            "FAIL",
            "Missing [gemini] api_key in private/appconfig.ini"
        )
        return dict(results=results, json=json)

    # --------------------------------------------------
    # 1. Client init
    # --------------------------------------------------
    try:
        client = GeminiLLMClient(api_key=api_key)
        add_result("Gemini client init", "PASS", {
            "model_name": client.model_name,
            "max_site_text_chars": client.max_site_text_chars,
            "temperature": client.temperature,
        })
    except Exception as e:
        add_result("Gemini client init", "FAIL", str(e))
        return dict(results=results, json=json)

    # --------------------------------------------------
    # 2. Real low-fit payload must stay conservative
    # --------------------------------------------------
    site_text_low = """
    Industrial equipment supplier.
    Product catalog, technical references, certifications, and distributor information.
    """

    business_context_low = {
        "niche": "service businesses",
        "city": "Marseille",
        "offer": "brand and website design",
        "signals": [],
        "output_language": "en",
    }

    try:
        payload = client.enrich_prospect(
            site_text=site_text_low,
            business_context=business_context_low,
        )
        validate_business_rules(payload, input_signals=business_context_low["signals"])

        add_result("Business rule - low fit stays conservative", "PASS", {
            "fit_confidence": payload["fit_confidence"],
            "email_subject": payload["email_subject"],
            "email_draft": payload["email_draft"],
            "cold_call_soft_close": payload["cold_call_soft_close"],
        })
    except Exception as e:
        add_result("Business rule - low fit stays conservative", "FAIL", str(e))

    # --------------------------------------------------
    # 3. Real strong-fit payload with contact evidence
    # --------------------------------------------------
    site_text_strong = """
    Modern dental clinic in Paris.
    Patients can book appointments online.
    The clinic offers cosmetic dentistry, implants, and emergency dental care.
    Practice Director: Dr. Claire Martin.
    Address: 28 rue Meslay, 75003 Paris, France.
    Contact: contact@clinic-example.com
    """

    business_context_strong = {
        "niche": "dentists",
        "city": "Paris",
        "offer": "website redesign and conversion optimization",
        "signals": [
            {
                "signal_type": "booking_detected",
                "signal_value": "online booking visible",
                "polarity": "positive",
                "source_kind": "rule",
                "confidence": 0.95,
                "reason": "Online booking is visible on the site.",
            }
        ],
        "output_language": "en",
    }

    try:
        payload = client.enrich_prospect(
            site_text=site_text_strong,
            business_context=business_context_strong,
        )
        validate_business_rules(payload, input_signals=business_context_strong["signals"])

        add_result("Business rule - explicit contact requires evidence", "PASS", {
            "contact_name": payload["contact_name"],
            "contact_role": payload["contact_role"],
            "address_text": payload["address_text"],
            "contact_evidence_text": payload["contact_evidence_text"],
        })
    except Exception as e:
        add_result("Business rule - explicit contact requires evidence", "FAIL", str(e))

    # --------------------------------------------------
    # 4. Synthetic invalid payload - contact without evidence must fail
    # --------------------------------------------------
    try:
        invalid_payload = {
            "business_summary": "Dental clinic in Paris.",
            "qualification_explanation": "Strong fit.",
            "fit_confidence": "high",
            "llm_business_type": "dental clinic",
            "llm_offer_fit": "Relevant because booking is visible.",
            "outreach_angle": "Booking flow optimization.",
            "email_framework_used": "reply_first_micro_pas",
            "email_subject": "booking question",
            "email_opening_line": "Noticed online booking on your site.",
            "email_draft": "Open to a quick look at that?",
            "derived_signals": [],
            "cold_call_framework_used": "permission_problem_binary_soft_close",
            "cold_call_opening": "Hi — cold call, brief one.",
            "cold_call_problem_hook": "Booking flow may matter here.",
            "cold_call_binary_question": "More traffic or better booking completion?",
            "cold_call_soft_close": "Could look at it in 10 minutes next week.",
            "cold_call_script": "Hi — cold call, brief one. Booking flow may matter here. More traffic or better booking completion? Could look at it in 10 minutes next week.",
            "contact_name": "Dr. Claire Martin",
            "contact_role": "Practice Director",
            "contact_name_confidence": "high",
            "address_text": "28 rue Meslay, 75003 Paris, France",
            "address_confidence": "high",
            "contact_evidence_text": "",
            "llm_model_used": "gemini-2.5-flash-lite",
        }

        validate_business_rules(invalid_payload, input_signals=[])
        add_result(
            "Business rule - reject contact without evidence",
            "FAIL",
            "Expected business validation failure was not raised"
        )
    except Exception as e:
        add_result("Business rule - reject contact without evidence", "PASS", str(e))

    # --------------------------------------------------
    # 5. Synthetic invalid payload - duplicate derived signal must fail
    # --------------------------------------------------
    try:
        input_signals = [
            {
                "signal_type": "booking_detected",
                "signal_value": "online booking visible",
                "polarity": "positive",
                "source_kind": "rule",
                "confidence": 0.95,
                "reason": "Online booking is visible."
            }
        ]

        invalid_payload = {
            "business_summary": "Dental clinic in Paris.",
            "qualification_explanation": "Strong fit.",
            "fit_confidence": "high",
            "llm_business_type": "dental clinic",
            "llm_offer_fit": "Relevant because booking is visible.",
            "outreach_angle": "Booking flow optimization.",
            "email_framework_used": "reply_first_micro_pas",
            "email_subject": "booking question",
            "email_opening_line": "Noticed online booking on your site.",
            "email_draft": "Open to a quick look at that?",
            "derived_signals": [
                {
                    "signal_type": "booking_detected",
                    "signal_value": "online booking visible",
                    "polarity": "positive",
                    "source_kind": "llm",
                    "confidence": 0.80,
                    "reason": "Duplicate of existing signal."
                }
            ],
            "cold_call_framework_used": "permission_problem_binary_soft_close",
            "cold_call_opening": "Hi — cold call, brief one.",
            "cold_call_problem_hook": "Booking flow may matter here.",
            "cold_call_binary_question": "More traffic or better booking completion?",
            "cold_call_soft_close": "Could look at it in 10 minutes next week.",
            "cold_call_script": "Hi — cold call, brief one. Booking flow may matter here. More traffic or better booking completion? Could look at it in 10 minutes next week.",
            "contact_name": "",
            "contact_role": "",
            "contact_name_confidence": "low",
            "address_text": "",
            "address_confidence": "low",
            "contact_evidence_text": "",
            "llm_model_used": "gemini-2.5-flash-lite",
        }

        validate_business_rules(invalid_payload, input_signals=input_signals)
        add_result(
            "Business rule - reject duplicate derived signal",
            "FAIL",
            "Expected business validation failure was not raised"
        )
    except Exception as e:
        add_result("Business rule - reject duplicate derived signal", "PASS", str(e))

    # --------------------------------------------------
    # 6. Synthetic invalid payload - low fit with hard CTA must fail
    # --------------------------------------------------
    try:
        invalid_payload = {
            "business_summary": "Industrial supplier.",
            "qualification_explanation": "Weak fit.",
            "fit_confidence": "low",
            "llm_business_type": "industrial equipment supplier",
            "llm_offer_fit": "Limited evidence of fit.",
            "outreach_angle": "Too little public information.",
            "email_framework_used": "reply_first_micro_pas",
            "email_subject": "quick question",
            "email_opening_line": "I had a quick look at your business.",
            "email_draft": "Book a demo with me this week and I’ll show you how we can transform your brand.",
            "derived_signals": [],
            "cold_call_framework_used": "permission_problem_binary_soft_close",
            "cold_call_opening": "Hi — cold call.",
            "cold_call_problem_hook": "We can transform your business fast.",
            "cold_call_binary_question": "Would Tuesday or Thursday work for a 30-minute demo?",
            "cold_call_soft_close": "Let’s book a 30-minute demo.",
            "cold_call_script": "Hi — cold call. Would Tuesday or Thursday work for a 30-minute demo? Let’s book a 30-minute demo.",
            "contact_name": "",
            "contact_role": "",
            "contact_name_confidence": "low",
            "address_text": "",
            "address_confidence": "low",
            "contact_evidence_text": "",
            "llm_model_used": "gemini-2.5-flash-lite",
        }

        validate_business_rules(invalid_payload, input_signals=[])
        add_result(
            "Business rule - reject hard CTA on low fit",
            "FAIL",
            "Expected business validation failure was not raised"
        )
    except Exception as e:
        add_result("Business rule - reject hard CTA on low fit", "PASS", str(e))

    # --------------------------------------------------
    # 7. Internal normalization test
    # --------------------------------------------------
    try:
        raw_parsed = {
            "business_summary": "A" * 1000,
            "qualification_explanation": "B" * 1000,
            "fit_confidence": "banana",
            "llm_business_type": "DENTAL CLINIC " * 20,
            "llm_offer_fit": "C" * 1000,
            "outreach_angle": "D" * 1000,
            "email_framework_used": "wrong_framework",
            "email_subject": "E" * 300,
            "email_opening_line": "F" * 500,
            "email_draft": "G" * 3000,
            "derived_signals": [
                {
                    "signal_type": "s1",
                    "signal_value": "v1",
                    "polarity": "positive",
                    "source_kind": "llm",
                    "confidence": 2.5,
                    "reason": "R1" * 100,
                },
                {
                    "signal_type": "s2",
                    "signal_value": "v2",
                    "polarity": "negative",
                    "source_kind": "llm",
                    "confidence": -1,
                    "reason": "R2" * 100,
                },
                {
                    "signal_type": "s3",
                    "signal_value": "v3",
                    "polarity": "unknown",
                    "source_kind": "llm",
                    "confidence": 0.2,
                    "reason": "R3" * 100,
                },
                {
                    "signal_type": "s4",
                    "signal_value": "v4",
                    "polarity": "positive",
                    "source_kind": "llm",
                    "confidence": 0.9,
                    "reason": "R4" * 100,
                },
            ],
            "cold_call_framework_used": "wrong_call_framework",
            "cold_call_opening": "H" * 500,
            "cold_call_problem_hook": "I" * 1000,
            "cold_call_binary_question": "J" * 1000,
            "cold_call_soft_close": "K" * 1000,
            "cold_call_script": "L" * 3000,
            "contact_name": "M" * 500,
            "contact_role": "N" * 500,
            "contact_name_confidence": "banana",
            "address_text": "O" * 1000,
            "address_confidence": "banana",
            "contact_evidence_text": "P" * 1000,
        }

        normalized = client._normalize_output(raw_parsed, business_context={"signals": []})

        checks = {
            "fit_confidence": normalized["fit_confidence"],
            "email_framework_used": normalized["email_framework_used"],
            "cold_call_framework_used": normalized["cold_call_framework_used"],
            "derived_signals_count": len(normalized["derived_signals"]),
            "first_confidence": normalized["derived_signals"][0]["confidence"],
            "second_confidence": normalized["derived_signals"][1]["confidence"],
            "business_summary_len": len(normalized["business_summary"]),
            "email_subject_len": len(normalized["email_subject"]),
            "email_draft_len": len(normalized["email_draft"]),
            "cold_call_script_len": len(normalized["cold_call_script"]),
            "contact_name_len": len(normalized["contact_name"]),
            "contact_evidence_text_len": len(normalized["contact_evidence_text"]),
        }

        if normalized["fit_confidence"] != "low":
            raise Exception("fit_confidence should default to low")

        if normalized["email_framework_used"] != "reply_first_micro_pas":
            raise Exception("email_framework_used normalization failed")

        if normalized["cold_call_framework_used"] != "permission_problem_binary_soft_close":
            raise Exception("cold_call_framework_used normalization failed")

        if len(normalized["derived_signals"]) != 3:
            raise Exception("derived_signals must be truncated to 3")

        if normalized["derived_signals"][0]["confidence"] != 1.0:
            raise Exception("confidence clipping upper bound failed")

        if normalized["derived_signals"][1]["confidence"] != 0.0:
            raise Exception("confidence clipping lower bound failed")

        if len(normalized["business_summary"]) > 400:
            raise Exception("business_summary truncation failed")

        if len(normalized["email_subject"]) > 80:
            raise Exception("email_subject truncation failed")

        if len(normalized["email_draft"]) > 900:
            raise Exception("email_draft truncation failed")

        if len(normalized["cold_call_script"]) > 1200:
            raise Exception("cold_call_script truncation failed")

        if len(normalized["contact_name"]) > 180:
            raise Exception("contact_name truncation failed")

        if len(normalized["contact_evidence_text"]) > 500:
            raise Exception("contact_evidence_text truncation failed")

        add_result("Business rule - internal normalization safeguards", "PASS", checks)
    except Exception as e:
        add_result("Business rule - internal normalization safeguards", "FAIL", str(e))

    return dict(results=results, json=json)




def test_gemini_llm_client_v41():
    import importlib
    from gluon.contrib.appconfig import AppConfig

    import applications.reasoningframe.modules.infrastructure.gemini_llm_client as gemini_module

    importlib.reload(gemini_module)

    GeminiLLMClient = gemini_module.GeminiLLMClient
    GeminiLLMClientError = gemini_module.GeminiLLMClientError

    myconf = AppConfig(reload=True)
    api_key = myconf.get("gemini.api_key")

    results = []

    def add_result(test_name, status, details):
        results.append({
            "test": test_name,
            "status": status,
            "details": details,
        })

    def validate_common_output(payload):
        required_keys = [
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
            "llm_model_used",
        ]

        missing = [k for k in required_keys if k not in payload]
        if missing:
            raise Exception("Missing keys: %s" % missing)

        if payload["fit_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid fit_confidence: %s" % payload["fit_confidence"])

        if payload["contact_name_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid contact_name_confidence: %s" % payload["contact_name_confidence"])

        if payload["address_confidence"] not in ("low", "medium", "high"):
            raise Exception("Invalid address_confidence: %s" % payload["address_confidence"])

        if payload["email_framework_used"] != "reply_first_micro_pas":
            raise Exception("Invalid email_framework_used: %s" % payload["email_framework_used"])

        if payload["cold_call_framework_used"] != "permission_problem_binary_soft_close":
            raise Exception("Invalid cold_call_framework_used: %s" % payload["cold_call_framework_used"])

        if not isinstance(payload["derived_signals"], list):
            raise Exception("derived_signals must be a list")

        if len(payload["derived_signals"]) > 3:
            raise Exception("derived_signals must contain at most 3 items")

        for i, sig in enumerate(payload["derived_signals"]):
            if sig.get("polarity") not in ("positive", "negative", "unknown"):
                raise Exception("Invalid polarity in derived_signals[%s]" % i)

            confidence = sig.get("confidence")
            if not isinstance(confidence, (int, float)):
                raise Exception("confidence must be numeric in derived_signals[%s]" % i)

            if confidence < 0.0 or confidence > 1.0:
                raise Exception("confidence out of range in derived_signals[%s]" % i)

            if sig.get("source_kind") != "llm":
                raise Exception("source_kind must be 'llm' in derived_signals[%s]" % i)

        # Champs texte minimaux
        for key in [
            "business_summary",
            "qualification_explanation",
            "llm_business_type",
            "llm_offer_fit",
            "outreach_angle",
            "email_subject",
            "email_opening_line",
            "email_draft",
            "cold_call_opening",
            "cold_call_problem_hook",
            "cold_call_binary_question",
            "cold_call_soft_close",
            "cold_call_script",
            "contact_name",
            "contact_role",
            "address_text",
            "contact_evidence_text",
            "llm_model_used",
        ]:
            if not isinstance(payload.get(key), str):
                raise Exception("%s must be a string" % key)

        # Contrôle de cohérence contact
        if payload["contact_name"] or payload["contact_role"] or payload["address_text"]:
            if not payload["contact_evidence_text"]:
                raise Exception("contact_evidence_text is required when contact fields are present")

        return True

    # --------------------------------------------------
    # 0. API key presence
    # --------------------------------------------------
    if not api_key:
        add_result(
            "Gemini API key presence",
            "FAIL",
            "Missing [gemini] api_key in private/appconfig.ini"
        )
        return dict(results=results)

    # --------------------------------------------------
    # 1. Client init
    # --------------------------------------------------
    try:
        client = GeminiLLMClient(api_key=api_key)
        add_result("Gemini client init", "PASS", {
            "model_name": client.model_name,
            "max_site_text_chars": client.max_site_text_chars,
            "temperature": client.temperature,
        })
    except Exception as e:
        add_result("Gemini client init", "FAIL", str(e))
        return dict(results=results)

    # --------------------------------------------------
    # 2. Strong fit + explicit contact
    # --------------------------------------------------
    site_text_strong = """
    Modern dental clinic in Paris.
    Patients can book appointments online.
    The clinic offers cosmetic dentistry, implants, and emergency dental care.
    Practice Director: Dr. Claire Martin.
    Address: 28 rue Meslay, 75003 Paris, France.
    Contact: contact@clinic-example.com
    """

    business_context_strong = {
        "niche": "dentists",
        "city": "Paris",
        "offer": "website redesign and conversion optimization",
        "signals": [
            {
                "signal_type": "booking_detected",
                "signal_value": "online booking visible",
                "polarity": "positive",
                "source_kind": "rule",
                "confidence": 0.95,
                "reason": "Online booking is visible on the site.",
            }
        ],
        "output_language": "en",
    }

    try:
        payload = client.enrich_prospect(
            site_text=site_text_strong,
            business_context=business_context_strong,
        )
        validate_common_output(payload)

        add_result("Gemini V4.1 strong fit with explicit contact", "PASS", {
            "fit_confidence": payload["fit_confidence"],
            "email_subject": payload["email_subject"],
            "email_opening_line": payload["email_opening_line"],
            "cold_call_opening": payload["cold_call_opening"],
            "contact_name": payload["contact_name"],
            "contact_role": payload["contact_role"],
            "address_text": payload["address_text"],
            "derived_signals_count": len(payload["derived_signals"]),
        })
    except Exception as e:
        add_result("Gemini V4.1 strong fit with explicit contact", "FAIL", str(e))

    # --------------------------------------------------
    # 3. Medium fit
    # --------------------------------------------------
    site_text_medium = """
    Digital product agency in Lyon.
    We design and build SaaS platforms, e-commerce sites, mobile apps,
    backend systems, QA workflows, and support projects for clients across Europe.
    """

    business_context_medium = {
        "niche": "digital agencies",
        "city": "Lyon",
        "offer": "white-label software subcontracting",
        "signals": [
            {
                "signal_type": "multi_service_delivery",
                "signal_value": "web mobile backend qa support",
                "polarity": "positive",
                "source_kind": "rule",
                "confidence": 0.88,
                "reason": "The site lists multiple delivery capabilities and client project work.",
            }
        ],
        "output_language": "en",
    }

    try:
        payload = client.enrich_prospect(
            site_text=site_text_medium,
            business_context=business_context_medium,
        )
        validate_common_output(payload)

        add_result("Gemini V4.1 medium fit", "PASS", {
            "fit_confidence": payload["fit_confidence"],
            "outreach_angle": payload["outreach_angle"],
            "email_subject": payload["email_subject"],
            "cold_call_binary_question": payload["cold_call_binary_question"],
            "contact_name": payload["contact_name"],
            "derived_signals_count": len(payload["derived_signals"]),
        })
    except Exception as e:
        add_result("Gemini V4.1 medium fit", "FAIL", str(e))

    # --------------------------------------------------
    # 4. Low fit
    # --------------------------------------------------
    site_text_low = """
    Industrial equipment supplier.
    Product catalog, technical references, certifications, and distributor information.
    """

    business_context_low = {
        "niche": "service businesses",
        "city": "Marseille",
        "offer": "brand and website design",
        "signals": [],
        "output_language": "en",
    }

    try:
        payload = client.enrich_prospect(
            site_text=site_text_low,
            business_context=business_context_low,
        )
        validate_common_output(payload)

        add_result("Gemini V4.1 low fit", "PASS", {
            "fit_confidence": payload["fit_confidence"],
            "qualification_explanation": payload["qualification_explanation"],
            "email_draft": payload["email_draft"],
            "cold_call_problem_hook": payload["cold_call_problem_hook"],
            "derived_signals_count": len(payload["derived_signals"]),
        })
    except Exception as e:
        add_result("Gemini V4.1 low fit", "FAIL", str(e))

    # --------------------------------------------------
    # 5. Empty site_text should fail
    # --------------------------------------------------
    try:
        client.enrich_prospect(
            site_text="",
            business_context={
                "niche": "dentists",
                "city": "Paris",
                "offer": "website redesign",
                "output_language": "en",
            },
        )
        add_result(
            "Gemini V4.1 empty site_text",
            "FAIL",
            "Expected exception was not raised"
        )
    except Exception as e:
        add_result("Gemini V4.1 empty site_text", "PASS", str(e))

    return dict(results=results)


def test_gemini_llm_client():
    import importlib
    from gluon.contrib.appconfig import AppConfig

    import applications.reasoningframe.modules.infrastructure.gemini_llm_client as gemini_module

    importlib.reload(gemini_module)

    GeminiLLMClient = gemini_module.GeminiLLMClient

    myconf = AppConfig(reload=True)
    api_key = myconf.get("gemini.api_key")

    results = []

    if not api_key:
        results.append({
            "test": "Gemini API key presence",
            "status": "FAIL",
            "details": "Missing [gemini] api_key in private/appconfig.ini",
        })
        return dict(results=results)

    try:
        client = GeminiLLMClient(api_key=api_key)
        results.append({
            "test": "Gemini client init",
            "status": "PASS",
            "details": {
                "model_name": client.model_name,
                "max_site_text_chars": client.max_site_text_chars,
                "temperature": client.temperature,
            },
        })
    except Exception as e:
        results.append({
            "test": "Gemini client init",
            "status": "FAIL",
            "details": str(e),
        })
        return dict(results=results)

    # --------------------------------------------------
    # Test 1 - English forced via output_language
    # --------------------------------------------------
    site_text_en = """
    Paris Dental Studios is a modern dental clinic in Paris.
    Patients can book appointments online.
    The clinic offers cosmetic dentistry, implants, and emergency dental care.
    Contact: contact@parisdentalstudios.com
    Phone: +33 1 23 45 67 89
    Address: 28 rue Meslay, 75003 Paris, France
    """

    business_context_en = {
        "niche": "dentists",
        "city": "Paris",
        "offer": "website redesign and conversion optimization",
        "signals": [
            {
                "signal_type": "booking_detected",
                "signal_value": "online booking visible",
                "polarity": "positive",
                "source_kind": "rule",
                "confidence": 0.95,
                "reason": "The website mentions appointments can be booked online.",
            }
        ],
        "output_language": "en",
    }

    try:
        payload = client.enrich_prospect(
            site_text=site_text_en,
            business_context=business_context_en,
        )
        results.append({
            "test": "Gemini enrich_prospect forced English",
            "status": "PASS",
            "details": payload,
        })
    except Exception as e:
        results.append({
            "test": "Gemini enrich_prospect forced English",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # Test 2 - French source without explicit output_language
    # --------------------------------------------------
    site_text_fr = """
    Paris Dental Studios est une clinique dentaire moderne à Paris.
    Les patients peuvent prendre rendez-vous en ligne.
    La clinique propose de la dentisterie esthétique, des implants et des soins dentaires d'urgence.
    Contact : contact@parisdentalstudios.com
    Téléphone : +33 1 23 45 67 89
    Adresse : 28 rue Meslay, 75003 Paris, France
    """

    business_context_fr = {
        "niche": "dentistes",
        "city": "Paris",
        "offer": "refonte de site web et optimisation de conversion",
        "signals": [
            {
                "signal_type": "booking_detected",
                "signal_value": "prise de rendez-vous en ligne visible",
                "polarity": "positive",
                "source_kind": "rule",
                "confidence": 0.95,
                "reason": "Le site mentionne la prise de rendez-vous en ligne.",
            }
        ],
        # no output_language on purpose
    }

    try:
        payload = client.enrich_prospect(
            site_text=site_text_fr,
            business_context=business_context_fr,
        )
        results.append({
            "test": "Gemini enrich_prospect French auto language",
            "status": "PASS",
            "details": payload,
        })
    except Exception as e:
        results.append({
            "test": "Gemini enrich_prospect French auto language",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # Test 3 - Minimal / sparse content
    # --------------------------------------------------
    site_text_sparse = """
    Local clinic in Lyon.
    Contact us.
    """

    business_context_sparse = {
        "niche": "clinics",
        "city": "Lyon",
        "offer": "website redesign",
        "signals": [],
    }

    try:
        payload = client.enrich_prospect(
            site_text=site_text_sparse,
            business_context=business_context_sparse,
        )
        results.append({
            "test": "Gemini enrich_prospect sparse content",
            "status": "PASS",
            "details": payload,
        })
    except Exception as e:
        results.append({
            "test": "Gemini enrich_prospect sparse content",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # Test 4 - Empty site_text should fail
    # --------------------------------------------------
    try:
        payload = client.enrich_prospect(
            site_text="",
            business_context={"niche": "dentists", "city": "Paris", "offer": "website redesign"},
        )
        results.append({
            "test": "Gemini enrich_prospect empty site_text",
            "status": "FAIL",
            "details": payload,
        })
    except Exception as e:
        results.append({
            "test": "Gemini enrich_prospect empty site_text",
            "status": "PASS",
            "details": str(e),
        })

    return dict(results=results)







def test_requests_fetcher():
    import importlib
    import applications.reasoningframe.modules.infrastructure.requests_fetcher as fetcher_module

    importlib.reload(fetcher_module)

    RequestsWebPageFetcher = fetcher_module.RequestsWebPageFetcher

    fetcher = RequestsWebPageFetcher()

    results = []

    # --------------------------------------------------
    # 1. Fetch homepage
    # --------------------------------------------------
    try:
        page = fetcher.fetch_page("https://parisdentalstudios.com")
        results.append({
            "test": "fetch_page homepage",
            "status": "PASS",
            "details": {
                "url": page["url"],
                "loaded": page["loaded"],
                "http_status": page["http_status"],
                "text_preview": page["extracted_text"][:500],
                "error_message": page["error_message"],
            },
        })
    except Exception as e:
        results.append({
            "test": "fetch_page homepage",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 2. Find contact page
    # --------------------------------------------------
    try:
        contact_url = fetcher.find_contact_page_url("https://parisdentalstudios.com")
        results.append({
            "test": "find_contact_page_url",
            "status": "PASS",
            "details": contact_url,
        })
    except Exception as e:
        results.append({
            "test": "find_contact_page_url",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 3. Invalid URL
    # --------------------------------------------------
    try:
        bad_page = fetcher.fetch_page("https://this-domain-should-not-exist-xyz-123.com")
        results.append({
            "test": "fetch_page invalid url",
            "status": "PASS",
            "details": bad_page,
        })
    except Exception as e:
        results.append({
            "test": "fetch_page invalid url",
            "status": "FAIL",
            "details": str(e),
        })

    return dict(results=results)


def test_brave_search_provider():
    import importlib
    from gluon.contrib.appconfig import AppConfig

    import applications.reasoningframe.modules.infrastructure.brave_search_provider as brave_module
    importlib.reload(brave_module)

    BraveSearchProvider = brave_module.BraveSearchProvider

    myconf = AppConfig(reload=True)
    api_key = myconf.get("brave.api_key")

    provider = BraveSearchProvider(api_key=api_key)

    results = []
    try:
        data = provider.search("dentists in Paris", limit=5)
        results.append({
            "test": "Brave search request",
            "status": "PASS",
            "details": data,
        })
    except Exception as e:
        results.append({
            "test": "Brave search request",
            "status": "FAIL",
            "details": str(e),
        })

    return dict(results=results)



import uuid


def test_v2_full_regression():
    import importlib
    import uuid

    import applications.reasoningframe.modules.application.validators as app_validators
    import applications.reasoningframe.modules.application.run_service as app_run_service
    import applications.reasoningframe.modules.application.prospect_service as app_prospect_service

    importlib.reload(app_validators)
    importlib.reload(app_run_service)
    importlib.reload(app_prospect_service)

    SearchRequestValidator = app_validators.SearchRequestValidator
    QualificationCriteriaValidator = app_validators.QualificationCriteriaValidator
    RunWorkflowValidator = app_validators.RunWorkflowValidator
    ProspectOutputValidator = app_validators.ProspectOutputValidator

    RunService = app_run_service.RunService
    RunServiceError = app_run_service.RunServiceError
    RunNotFoundError = app_run_service.RunNotFoundError

    ProspectService = app_prospect_service.ProspectService
    ProspectServiceError = app_prospect_service.ProspectServiceError

    results = []

    def add_result(test_name, status, details):
        results.append({
            "test": test_name,
            "status": status,
            "details": details,
        })

    run_id = None
    prospect_id = None

    # --------------------------------------------------
    # A. MODELS V2 - POSITIVE TEST
    # --------------------------------------------------
    try:
        run_ret = db.prospect_run.validate_and_insert(
            run_uuid=str(uuid.uuid4()),
            niche="dentists",
            city="Paris",
            offer="website redesign",
            status="idle",
            payment_status="pending",
            is_unlocked=False,
            preview_count=3,
            requested_result_limit=25,
            discovered_count=0,
            processed_count=0,
            error_count=0,
        )
        if run_ret.get("errors"):
            add_result("MODEL V2 prospect_run insert", "FAIL", run_ret.get("errors"))
            return dict(results=results)

        run_id = run_ret.get("id")

        prospect_ret = db.prospect.validate_and_insert(
            run_id=run_id,
            company_name="Cabinet Dentaire Paris Centre",
            domain="https://example.com",
            city="Paris",
            qualification_status="uncertain",
            fit_confidence="medium",
            qualification_explanation="Initial qualification pending.",
            llm_business_type="clinic",
            llm_offer_fit="Likely a good fit for website redesign.",
            render_order=0,
        )
        if prospect_ret.get("errors"):
            add_result("MODEL V2 prospect insert", "FAIL", prospect_ret.get("errors"))
            return dict(results=results)

        prospect_id = prospect_ret.get("id")

        source_ret = db.prospect_source_page.validate_and_insert(
            prospect_id=prospect_id,
            url="https://example.com",
            page_type="homepage",
            loaded=True,
            http_status=200,
            extracted_text="Welcome to our dental clinic in Paris. Book online today.",
        )
        if source_ret.get("errors"):
            add_result("MODEL V2 source page insert", "FAIL", source_ret.get("errors"))
            return dict(results=results)

        contact_ret = db.prospect_contact.validate_and_insert(
            prospect_id=prospect_id,
            contact_type="email",
            value="hello@example.com",
            source_url="https://example.com/contact",
            confidence=0.9,
            is_primary=True,
        )
        if contact_ret.get("errors"):
            add_result("MODEL V2 contact insert", "FAIL", contact_ret.get("errors"))
            return dict(results=results)

        signal_ret = db.prospect_signal.validate_and_insert(
            prospect_id=prospect_id,
            signal_type="llm_fit",
            signal_value="strong local service fit",
            polarity="positive",
            source_kind="llm",
            confidence=0.92,
            reason="The business is a local clinic with visible booking intent.",
        )
        if signal_ret.get("errors"):
            add_result("MODEL V2 signal insert", "FAIL", signal_ret.get("errors"))
            return dict(results=results)

        artifact_ret = db.prospect_artifact.validate_and_insert(
            prospect_id=prospect_id,
            business_summary="Local dental clinic in Paris.",
            qualification_explanation="The clinic is a strong fit because it serves local customers and depends on bookings.",
            fit_confidence="high",
            outreach_angle="Improve local conversion and booking flow.",
            email_subject="Quick idea for your clinic website",
            email_draft="Hi, I noticed your clinic site and had a quick idea to improve booking conversion.",
            llm_model_used="gemini-2.5-flash-lite",
        )
        if artifact_ret.get("errors"):
            add_result("MODEL V2 artifact insert", "FAIL", artifact_ret.get("errors"))
            return dict(results=results)

        db.commit()

        run = db.prospect_run(run_id)
        prospect = db.prospect(prospect_id)
        signal = db(db.prospect_signal.prospect_id == prospect_id).select().first()
        artifact = db(db.prospect_artifact.prospect_id == prospect_id).select().first()

        add_result("MODEL V2 positive insert chain", "PASS", {
            "run_id": run.id if run else None,
            "prospect_id": prospect.id if prospect else None,
            "fit_confidence": prospect.fit_confidence if prospect else None,
            "signal_source_kind": signal.source_kind if signal else None,
            "artifact_fit_confidence": artifact.fit_confidence if artifact else None,
            "llm_model_used": artifact.llm_model_used if artifact else None,
        })

    except Exception as e:
        add_result("MODEL V2 positive insert chain", "FAIL", str(e))

    # --------------------------------------------------
    # A.1 MODELS V2.1 - ENRICHED CONTACT TEST
    # --------------------------------------------------
    try:
        if not prospect_id:
            raise Exception("prospect_id is missing for enriched contact test")

        ret = db.prospect_contact.validate_and_insert(
            prospect_id=prospect_id,
            contact_type="email",
            value="contact@example.com",
            contact_name="Dr. Jane Doe",
            contact_role="Dentist",
            address_text="12 rue Exemple, 75012 Paris, France",
            evidence_text="Dr. Jane Doe welcomes you to her dental office.",
            source_url="https://example.com/contact",
            confidence=0.95,
            is_primary=False,
        )

        if ret.get("errors"):
            add_result("MODEL V2.1 prospect_contact enriched insert", "FAIL", ret.get("errors"))
        else:
            db.commit()
            contact_row = db.prospect_contact(ret.get("id"))
            add_result("MODEL V2.1 prospect_contact enriched insert", "PASS", {
                "id": contact_row.id,
                "contact_name": contact_row.contact_name,
                "contact_role": contact_row.contact_role,
                "address_text": contact_row.address_text,
                "evidence_text": contact_row.evidence_text,
            })
    except Exception as e:
        add_result("MODEL V2.1 prospect_contact enriched insert", "FAIL", str(e))

    # --------------------------------------------------
    # B. MODELS V2 - NEGATIVE TESTS
    # --------------------------------------------------
    try:
        ret = db.prospect.validate_and_insert(
            run_id=run_id,
            company_name="Bad Prospect",
            domain="https://bad.example",
            fit_confidence="super_high",
        )
        if ret.get("errors"):
            add_result("MODEL V2 invalid fit_confidence", "PASS", ret.get("errors"))
        else:
            add_result("MODEL V2 invalid fit_confidence", "FAIL", "Expected validation error was not raised")
    except Exception as e:
        add_result("MODEL V2 invalid fit_confidence", "FAIL", str(e))

    try:
        ret = db.prospect_signal.validate_and_insert(
            prospect_id=prospect_id,
            signal_type="bad_signal",
            polarity="positive",
            source_kind="magic",
        )
        if ret.get("errors"):
            add_result("MODEL V2 invalid signal source_kind", "PASS", ret.get("errors"))
        else:
            add_result("MODEL V2 invalid signal source_kind", "FAIL", "Expected validation error was not raised")
    except Exception as e:
        add_result("MODEL V2 invalid signal source_kind", "FAIL", str(e))

    try:
        ret = db.prospect_artifact.validate_and_insert(
            prospect_id=99999999,
            qualification_explanation="Fake",
            fit_confidence="high",
        )
        if ret.get("errors"):
            add_result("MODEL V2 invalid artifact prospect_id", "PASS", ret.get("errors"))
        else:
            add_result("MODEL V2 invalid artifact prospect_id", "FAIL", "Expected validation error was not raised")
    except Exception as e:
        add_result("MODEL V2 invalid artifact prospect_id", "FAIL", str(e))

    # --------------------------------------------------
    # C. VALIDATORS V2
    # --------------------------------------------------
    try:
        validator = SearchRequestValidator()
        clean = validator.validate(
            niche="   dentists   ",
            city="  Paris ",
            offer="  website redesign for local clinics ",
            requested_result_limit="25",
        )
        add_result("VALIDATOR SearchRequestValidator valid", "PASS", clean)
    except Exception as e:
        add_result("VALIDATOR SearchRequestValidator valid", "FAIL", str(e))

    try:
        criteria_validator = QualificationCriteriaValidator()
        parsed = criteria_validator.validate("""
must_mention:booking
must_not_mention:klaviyo
must_mention:booking
        """)
        add_result("VALIDATOR QualificationCriteriaValidator dedupe", "PASS", parsed)
    except Exception as e:
        add_result("VALIDATOR QualificationCriteriaValidator dedupe", "FAIL", str(e))

    try:
        output_validator = ProspectOutputValidator()
        clean_output = output_validator.validate_all(
            summary="",
            angle=" weak CTA on homepage ",
            subject="",
            draft=None,
            qualification_explanation="",
            fit_confidence="banana",
        )
        add_result("VALIDATOR ProspectOutputValidator V2 fallback", "PASS", clean_output)
    except Exception as e:
        add_result("VALIDATOR ProspectOutputValidator V2 fallback", "FAIL", str(e))

    # --------------------------------------------------
    # D. RUN SERVICE V2
    # --------------------------------------------------
    try:
        run_service = RunService(
            db=db,
            search_request_validator=SearchRequestValidator(),
            criteria_validator=QualificationCriteriaValidator(),
            workflow_validator=RunWorkflowValidator(),
        )

        service_run = run_service.create_run(
            niche="lawyers",
            city="Lyon",
            offer="lead generation service",
            raw_criteria="""
must_mention:contact
must_not_mention:klaviyo
            """,
            requested_result_limit=10,
        )

        add_result("RUN SERVICE create_run", "PASS", {
            "id": service_run.id,
            "status": service_run.status,
            "city": service_run.city,
        })

        updated = run_service.update_status(service_run.id, "searching")
        add_result("RUN SERVICE update_status", "PASS", {"status": updated.status})

        updated = run_service.increment_discovered_count(service_run.id, amount=5)
        add_result("RUN SERVICE increment_discovered_count", "PASS", {"discovered_count": updated.discovered_count})

        updated = run_service.increment_processed_count(service_run.id, amount=3)
        add_result("RUN SERVICE increment_processed_count", "PASS", {"processed_count": updated.processed_count})

        updated = run_service.increment_error_count(service_run.id, amount=1, last_error_message="Test V2 error")
        add_result("RUN SERVICE increment_error_count", "PASS", {
            "error_count": updated.error_count,
            "last_error_message": updated.last_error_message,
        })

        updated = run_service.set_search_query_built(service_run.id, "lawyers in Lyon")
        add_result("RUN SERVICE set_search_query_built", "PASS", {"search_query_built": updated.search_query_built})

        updated = run_service.mark_unlocked(service_run.id)
        add_result("RUN SERVICE mark_unlocked", "PASS", {
            "is_unlocked": updated.is_unlocked,
            "payment_status": updated.payment_status,
            "status": updated.status,
        })

        updated = run_service.mark_exported(service_run.id, "/tmp/v2_run_export.csv")
        add_result("RUN SERVICE mark_exported", "PASS", {
            "status": updated.status,
            "exported_csv_path": updated.exported_csv_path,
        })

        try:
            run_service.update_status(service_run.id, "invalid_status")
            add_result("RUN SERVICE invalid status rejected", "FAIL", "Expected exception was not raised")
        except Exception as e:
            add_result("RUN SERVICE invalid status rejected", "PASS", str(e))

    except Exception as e:
        add_result("RUN SERVICE V2 full flow", "FAIL", str(e))

    # --------------------------------------------------
    # E. PROSPECT SERVICE V2
    # --------------------------------------------------
    try:
        prospect_service = ProspectService(db=db)

        run_for_prospect = db.prospect_run.validate_and_insert(
            run_uuid=str(uuid.uuid4()),
            niche="plumbers",
            city="Marseille",
            offer="conversion optimization",
            status="idle",
            payment_status="pending",
            is_unlocked=False,
            preview_count=3,
            requested_result_limit=25,
            discovered_count=0,
            processed_count=0,
            error_count=0,
        )
        if run_for_prospect.get("errors"):
            raise Exception(run_for_prospect.get("errors"))

        prospect_run_id = run_for_prospect.get("id")

        ps_prospect = prospect_service.create_prospect(
            run_id=prospect_run_id,
            company_name="Plomberie Marseille Express",
            domain="https://plomberie-marseille.example",
            city="Marseille",
            render_order=1,
        )

        ps_source = prospect_service.add_source_page(
            prospect_id=ps_prospect.id,
            url="https://plomberie-marseille.example",
            page_type="homepage",
            loaded=True,
            http_status=200,
            extracted_text="Emergency plumbing in Marseille. Call us today.",
        )

        ps_contact = prospect_service.add_contact(
            prospect_id=ps_prospect.id,
            contact_type="phone",
            value="+33123456789",
            source_url="https://plomberie-marseille.example/contact",
            confidence=0.8,
            is_primary=True,
            contact_name="Jean Dupont",
            contact_role="Founder",
            address_text="8 rue Exemple, 13001 Marseille, France",
            evidence_text="Jean Dupont, founder, can be reached by phone for urgent interventions.",
        )

        ps_signal = prospect_service.add_signal(
            prospect_id=ps_prospect.id,
            signal_type="local_service_fit",
            signal_value="strong",
            polarity="positive",
            source_kind="llm",
            confidence=0.91,
            reason="Strong local service business fit.",
        )

        ps_artifact = prospect_service.replace_artifact(
            prospect_id=ps_prospect.id,
            business_summary="Local plumbing business in Marseille.",
            qualification_explanation="Strong fit because the business serves local urgent demand.",
            fit_confidence="high",
            outreach_angle="Improve local lead capture from mobile traffic.",
            email_subject="Quick idea for your plumbing website",
            email_draft="Hi, I had a quick idea to improve the way emergency plumbing leads convert from mobile visitors.",
            llm_model_used="gemini-2.5-flash-lite",
        )

        ps_best = prospect_service.set_best_contact(
            prospect_id=ps_prospect.id,
            best_contact_value="+33123456789",
            has_public_contact=True,
        )

        ps_qual = prospect_service.set_qualification(
            prospect_id=ps_prospect.id,
            qualification_status="qualified",
            qualification_explanation="Strong local fit for conversion optimization.",
            fit_confidence="high",
            llm_business_type="local_service_business",
            llm_offer_fit="Strong fit for website conversion improvement.",
        )

        ps_processed = prospect_service.set_processed(ps_prospect.id, True)

        add_result("PROSPECT SERVICE V2 full flow", "PASS", {
            "prospect_id": ps_prospect.id,
            "source_id": ps_source.id,
            "contact_id": ps_contact.id,
            "signal_id": ps_signal.id,
            "artifact_id": ps_artifact.id if ps_artifact else None,
            "best_contact_value": ps_best.best_contact_value,
            "qualification_status": ps_qual.qualification_status,
            "fit_confidence": ps_qual.fit_confidence,
            "is_processed": ps_processed.is_processed,
            "contact_name": ps_contact.contact_name,
            "contact_role": ps_contact.contact_role,
            "address_text": ps_contact.address_text,
        })

        try:
            prospect_service.add_signal(
                prospect_id=ps_prospect.id,
                signal_type="broken_signal",
                signal_value="x",
                polarity="positive",
                source_kind="invalid_source_kind",
                confidence=0.5,
                reason="Should fail",
            )
            add_result("PROSPECT SERVICE invalid source_kind rejected", "FAIL", "Expected exception was not raised")
        except Exception as e:
            add_result("PROSPECT SERVICE invalid source_kind rejected", "PASS", str(e))

    except Exception as e:
        add_result("PROSPECT SERVICE V2 full flow", "FAIL", str(e))

    return dict(results=results)





def test_run_service():
    import importlib
    import applications.reasoningframe.modules.application.validators as app_validators
    import applications.reasoningframe.modules.application.run_service as app_run_service

    importlib.reload(app_validators)
    importlib.reload(app_run_service)

    SearchRequestValidator = app_validators.SearchRequestValidator
    QualificationCriteriaValidator = app_validators.QualificationCriteriaValidator
    RunWorkflowValidator = app_validators.RunWorkflowValidator

    RunService = app_run_service.RunService
    RunServiceError = app_run_service.RunServiceError
    RunNotFoundError = app_run_service.RunNotFoundError

    results = []

    run_service = RunService(
        db=db,
        search_request_validator=SearchRequestValidator(),
        criteria_validator=QualificationCriteriaValidator(),
        workflow_validator=RunWorkflowValidator(),
    )

    # --------------------------------------------------
    # 1. create_run valid
    # --------------------------------------------------
    created_run = None
    try:
        created_run = run_service.create_run(
            niche="   dentists   ",
            city=" Paris ",
            offer=" website redesign ",
            raw_criteria="""
must_mention:booking
must_not_mention:klaviyo
            """,
            requested_result_limit="25",
        )
        results.append({
            "test": "create_run valid",
            "status": "PASS",
            "details": {
                "id": created_run.id,
                "niche": created_run.niche,
                "city": created_run.city,
                "offer": created_run.offer,
                "status": created_run.status,
                "payment_status": created_run.payment_status,
                "requested_result_limit": created_run.requested_result_limit,
            }
        })
    except Exception as e:
        results.append({
            "test": "create_run valid",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 2. create_run invalid input
    # --------------------------------------------------
    try:
        run_service.create_run(
            niche="",
            city="Paris",
            offer="website redesign",
            raw_criteria=None,
            requested_result_limit=25,
        )
        results.append({
            "test": "create_run invalid input",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except Exception as e:
        results.append({
            "test": "create_run invalid input",
            "status": "PASS",
            "details": str(e),
        })

    # --------------------------------------------------
    # 3. get_run_or_fail valid
    # --------------------------------------------------
    try:
        fetched = run_service.get_run_or_fail(created_run.id)
        results.append({
            "test": "get_run_or_fail valid",
            "status": "PASS",
            "details": {
                "id": fetched.id,
                "run_uuid": fetched.run_uuid,
            },
        })
    except Exception as e:
        results.append({
            "test": "get_run_or_fail valid",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 4. get_run_or_fail invalid
    # --------------------------------------------------
    try:
        run_service.get_run_or_fail(99999999)
        results.append({
            "test": "get_run_or_fail invalid",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except RunNotFoundError as e:
        results.append({
            "test": "get_run_or_fail invalid",
            "status": "PASS",
            "details": str(e),
        })
    except Exception as e:
        results.append({
            "test": "get_run_or_fail invalid",
            "status": "FAIL",
            "details": "Wrong exception: %s" % e,
        })

    # --------------------------------------------------
    # 5. get_run_parsed_criteria
    # --------------------------------------------------
    try:
        parsed = run_service.get_run_parsed_criteria(created_run)
        results.append({
            "test": "get_run_parsed_criteria",
            "status": "PASS",
            "details": parsed,
        })
    except Exception as e:
        results.append({
            "test": "get_run_parsed_criteria",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 6. update_status valid
    # --------------------------------------------------
    try:
        updated = run_service.update_status(created_run.id, "searching")
        results.append({
            "test": "update_status valid",
            "status": "PASS",
            "details": {"status": updated.status},
        })
    except Exception as e:
        results.append({
            "test": "update_status valid",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 7. update_status invalid
    # --------------------------------------------------
    try:
        run_service.update_status(created_run.id, "banana_status")
        results.append({
            "test": "update_status invalid",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except RunServiceError as e:
        results.append({
            "test": "update_status invalid",
            "status": "PASS",
            "details": str(e),
        })
    except Exception as e:
        results.append({
            "test": "update_status invalid",
            "status": "FAIL",
            "details": "Wrong exception: %s" % e,
        })

    # --------------------------------------------------
    # 8. mark_locked_preview
    # --------------------------------------------------
    try:
        updated = run_service.mark_locked_preview(created_run.id)
        results.append({
            "test": "mark_locked_preview",
            "status": "PASS",
            "details": {"status": updated.status},
        })
    except Exception as e:
        results.append({
            "test": "mark_locked_preview",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 9. increment_discovered_count
    # --------------------------------------------------
    try:
        updated = run_service.increment_discovered_count(created_run.id, amount=3)
        results.append({
            "test": "increment_discovered_count",
            "status": "PASS",
            "details": {"discovered_count": updated.discovered_count},
        })
    except Exception as e:
        results.append({
            "test": "increment_discovered_count",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 10. increment_processed_count
    # --------------------------------------------------
    try:
        updated = run_service.increment_processed_count(created_run.id, amount=2)
        results.append({
            "test": "increment_processed_count",
            "status": "PASS",
            "details": {"processed_count": updated.processed_count},
        })
    except Exception as e:
        results.append({
            "test": "increment_processed_count",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 11. increment_error_count
    # --------------------------------------------------
    try:
        updated = run_service.increment_error_count(
            created_run.id,
            amount=1,
            last_error_message="Test error message",
        )
        results.append({
            "test": "increment_error_count",
            "status": "PASS",
            "details": {
                "error_count": updated.error_count,
                "last_error_message": updated.last_error_message,
            },
        })
    except Exception as e:
        results.append({
            "test": "increment_error_count",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 12. increment_discovered_count invalid amount
    # --------------------------------------------------
    try:
        run_service.increment_discovered_count(created_run.id, amount=-1)
        results.append({
            "test": "increment_discovered_count invalid amount",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except RunServiceError as e:
        results.append({
            "test": "increment_discovered_count invalid amount",
            "status": "PASS",
            "details": str(e),
        })
    except Exception as e:
        results.append({
            "test": "increment_discovered_count invalid amount",
            "status": "FAIL",
            "details": "Wrong exception: %s" % e,
        })

    # --------------------------------------------------
    # 13. set_search_query_built
    # --------------------------------------------------
    try:
        updated = run_service.set_search_query_built(
            created_run.id,
            "dentists in Paris",
        )
        results.append({
            "test": "set_search_query_built",
            "status": "PASS",
            "details": {"search_query_built": updated.search_query_built},
        })
    except Exception as e:
        results.append({
            "test": "set_search_query_built",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 14. ensure_run_can_be_processed
    # --------------------------------------------------
    try:
        checked = run_service.ensure_run_can_be_processed(created_run.id)
        results.append({
            "test": "ensure_run_can_be_processed",
            "status": "PASS",
            "details": {"id": checked.id},
        })
    except Exception as e:
        results.append({
            "test": "ensure_run_can_be_processed",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 15. mark_unlocked valid
    # --------------------------------------------------
    try:
        updated = run_service.mark_unlocked(created_run.id)
        results.append({
            "test": "mark_unlocked valid",
            "status": "PASS",
            "details": {
                "is_unlocked": updated.is_unlocked,
                "payment_status": updated.payment_status,
                "status": updated.status,
            },
        })
    except Exception as e:
        results.append({
            "test": "mark_unlocked valid",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 16. mark_unlocked already unlocked
    # --------------------------------------------------
    try:
        run_service.mark_unlocked(created_run.id)
        results.append({
            "test": "mark_unlocked already unlocked",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except Exception as e:
        results.append({
            "test": "mark_unlocked already unlocked",
            "status": "PASS",
            "details": str(e),
        })

    # --------------------------------------------------
    # 17. ensure_run_can_export after unlock
    # --------------------------------------------------
    try:
        checked = run_service.ensure_run_can_export(created_run.id)
        results.append({
            "test": "ensure_run_can_export after unlock",
            "status": "PASS",
            "details": {"id": checked.id},
        })
    except Exception as e:
        results.append({
            "test": "ensure_run_can_export after unlock",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 18. mark_exported valid
    # --------------------------------------------------
    try:
        updated = run_service.mark_exported(
            created_run.id,
            "/tmp/test_export.csv",
        )
        results.append({
            "test": "mark_exported valid",
            "status": "PASS",
            "details": {
                "status": updated.status,
                "exported_csv_path": updated.exported_csv_path,
            },
        })
    except Exception as e:
        results.append({
            "test": "mark_exported valid",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 19. mark_exported locked run should fail
    # --------------------------------------------------
    try:
        locked_run = run_service.create_run(
            niche="lawyers",
            city="Lyon",
            offer="lead generation service",
            raw_criteria=None,
            requested_result_limit=10,
        )
        run_service.increment_processed_count(locked_run.id, amount=1)
        run_service.mark_exported(locked_run.id, "/tmp/locked.csv")
        results.append({
            "test": "mark_exported locked run should fail",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except Exception as e:
        results.append({
            "test": "mark_exported locked run should fail",
            "status": "PASS",
            "details": str(e),
        })

    return dict(results=results)



def test_application_validators():
    import importlib
    import applications.reasoningframe.modules.application.validators as app_validators

    importlib.reload(app_validators)

    SearchRequestValidator = app_validators.SearchRequestValidator
    QualificationCriteriaValidator = app_validators.QualificationCriteriaValidator
    RunWorkflowValidator = app_validators.RunWorkflowValidator
    ProspectOutputValidator = app_validators.ProspectOutputValidator

    results = []

    # --------------------------------------------------
    # 1. SearchRequestValidator - valid case
    # --------------------------------------------------
    try:
        validator = SearchRequestValidator()
        clean = validator.validate(
            niche="   dentists   ",
            city="  Paris ",
            offer="  website redesign for local clinics ",
            requested_result_limit="25",
        )
        results.append({
            "test": "SearchRequestValidator valid input",
            "status": "PASS",
            "details": clean,
        })
    except Exception as e:
        results.append({
            "test": "SearchRequestValidator valid input",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 2. SearchRequestValidator - invalid empty niche
    # --------------------------------------------------
    try:
        validator = SearchRequestValidator()
        validator.validate(
            niche="",
            city="Paris",
            offer="website redesign",
            requested_result_limit=25,
        )
        results.append({
            "test": "SearchRequestValidator invalid empty niche",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except Exception as e:
        results.append({
            "test": "SearchRequestValidator invalid empty niche",
            "status": "PASS",
            "details": str(e),
        })

    # --------------------------------------------------
    # 3. SearchRequestValidator - invalid limit
    # --------------------------------------------------
    try:
        validator = SearchRequestValidator()
        validator.validate(
            niche="dentists",
            city="Paris",
            offer="website redesign",
            requested_result_limit="9999",
        )
        results.append({
            "test": "SearchRequestValidator invalid limit",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except Exception as e:
        results.append({
            "test": "SearchRequestValidator invalid limit",
            "status": "PASS",
            "details": str(e),
        })

    # --------------------------------------------------
    # 4. QualificationCriteriaValidator - multiline input
    # --------------------------------------------------
    try:
        criteria_validator = QualificationCriteriaValidator()
        parsed = criteria_validator.validate("""
must_mention:shopify
must_not_mention:klaviyo
        """)
        results.append({
            "test": "QualificationCriteriaValidator multiline input",
            "status": "PASS",
            "details": parsed,
        })
    except Exception as e:
        results.append({
            "test": "QualificationCriteriaValidator multiline input",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 5. QualificationCriteriaValidator - comma separated input
    # --------------------------------------------------
    try:
        criteria_validator = QualificationCriteriaValidator()
        parsed = criteria_validator.validate("must_mention:shopify, must_not_mention:klaviyo")
        results.append({
            "test": "QualificationCriteriaValidator comma input",
            "status": "PASS",
            "details": parsed,
        })
    except Exception as e:
        results.append({
            "test": "QualificationCriteriaValidator comma input",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 6. QualificationCriteriaValidator - list input
    # --------------------------------------------------
    try:
        criteria_validator = QualificationCriteriaValidator()
        parsed = criteria_validator.validate([
            "must_mention:shopify",
            "must_not_mention:klaviyo",
            "must_mention:shopify",  # duplicate on purpose
        ])
        results.append({
            "test": "QualificationCriteriaValidator list input + dedupe",
            "status": "PASS",
            "details": parsed,
        })
    except Exception as e:
        results.append({
            "test": "QualificationCriteriaValidator list input + dedupe",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 7. QualificationCriteriaValidator - invalid format
    # --------------------------------------------------
    try:
        criteria_validator = QualificationCriteriaValidator()
        criteria_validator.validate("shopify")
        results.append({
            "test": "QualificationCriteriaValidator invalid format",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except Exception as e:
        results.append({
            "test": "QualificationCriteriaValidator invalid format",
            "status": "PASS",
            "details": str(e),
        })

    # --------------------------------------------------
    # 8. QualificationCriteriaValidator - invalid kind
    # --------------------------------------------------
    try:
        criteria_validator = QualificationCriteriaValidator()
        criteria_validator.validate("contains:shopify")
        results.append({
            "test": "QualificationCriteriaValidator invalid kind",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except Exception as e:
        results.append({
            "test": "QualificationCriteriaValidator invalid kind",
            "status": "PASS",
            "details": str(e),
        })

    # --------------------------------------------------
    # Prepare a run for workflow tests
    # --------------------------------------------------
    run_ret = db.prospect_run.validate_and_insert(
        run_uuid="workflow-test-run-001",
        niche="dentists",
        city="Paris",
        offer="website redesign",
        status="idle",
        payment_status="pending",
        is_unlocked=False,
        preview_count=3,
        requested_result_limit=25,
        discovered_count=1,
        processed_count=1,
        error_count=0,
    )

    workflow_run = None
    if not run_ret.get('errors'):
        workflow_run = db.prospect_run(run_ret.get('id'))

    empty_run_ret = db.prospect_run.validate_and_insert(
        run_uuid=str(uuid.uuid4()), # UUID dynamique,
        niche="dentists",
        city="Paris",
        offer="website redesign",
        status="idle",
        payment_status="pending",
        is_unlocked=False,
        preview_count=3,
        requested_result_limit=25,
        discovered_count=0,
        processed_count=0,
        error_count=0,
    )

    empty_run = None
    if not empty_run_ret.get('errors'): # CORRECTION ICI
        empty_run = db.prospect_run(empty_run_ret.get('id')) # CORRECTION ICI

    unlocked_run_ret = db.prospect_run.validate_and_insert(
        run_uuid=str(uuid.uuid4()), # UUID dynamique
        niche="dentists",
        city="Paris",
        offer="website redesign",
        status="unlocked",
        payment_status="paid",
        is_unlocked=True,
        preview_count=3,
        requested_result_limit=25,
        discovered_count=2,
        processed_count=2,
        error_count=0,
    )

    unlocked_run = None
    if not unlocked_run_ret.get('errors'): # CORRECTION ICI
        unlocked_run = db.prospect_run(unlocked_run_ret.get('id')) # CORRECTION ICI

    db.commit()

    # --------------------------------------------------
    # 9. RunWorkflowValidator - can process run
    # --------------------------------------------------
    try:
        workflow_validator = RunWorkflowValidator()
        workflow_validator.ensure_can_process_run(workflow_run)
        results.append({
            "test": "RunWorkflowValidator ensure_can_process_run valid",
            "status": "PASS",
            "details": "Run can be processed",
        })
    except Exception as e:
        results.append({
            "test": "RunWorkflowValidator ensure_can_process_run valid",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 10. RunWorkflowValidator - can unlock valid run
    # --------------------------------------------------
    try:
        workflow_validator = RunWorkflowValidator()
        workflow_validator.ensure_can_unlock(workflow_run)
        results.append({
            "test": "RunWorkflowValidator ensure_can_unlock valid",
            "status": "PASS",
            "details": "Run can be unlocked",
        })
    except Exception as e:
        results.append({
            "test": "RunWorkflowValidator ensure_can_unlock valid",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 11. RunWorkflowValidator - cannot unlock empty run
    # --------------------------------------------------
    try:
        workflow_validator = RunWorkflowValidator()
        workflow_validator.ensure_can_unlock(empty_run)
        results.append({
            "test": "RunWorkflowValidator ensure_can_unlock empty run",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except Exception as e:
        results.append({
            "test": "RunWorkflowValidator ensure_can_unlock empty run",
            "status": "PASS",
            "details": str(e),
        })

    # --------------------------------------------------
    # 12. RunWorkflowValidator - cannot export locked run
    # --------------------------------------------------
    try:
        workflow_validator = RunWorkflowValidator()
        workflow_validator.ensure_can_export(workflow_run)
        results.append({
            "test": "RunWorkflowValidator ensure_can_export locked run",
            "status": "FAIL",
            "details": "Expected exception was not raised",
        })
    except Exception as e:
        results.append({
            "test": "RunWorkflowValidator ensure_can_export locked run",
            "status": "PASS",
            "details": str(e),
        })

    # --------------------------------------------------
    # 13. RunWorkflowValidator - can export unlocked run
    # --------------------------------------------------
    try:
        workflow_validator = RunWorkflowValidator()
        workflow_validator.ensure_can_export(unlocked_run)
        results.append({
            "test": "RunWorkflowValidator ensure_can_export unlocked run",
            "status": "PASS",
            "details": "Run can be exported",
        })
    except Exception as e:
        results.append({
            "test": "RunWorkflowValidator ensure_can_export unlocked run",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 14. ProspectOutputValidator - full fallback behavior
    # --------------------------------------------------
    try:
        output_validator = ProspectOutputValidator()
        clean_output = output_validator.validate_all(
            summary="",
            angle="  weak CTA on homepage  ",
            subject="",
            draft=None,
        )
        results.append({
            "test": "ProspectOutputValidator fallback behavior",
            "status": "PASS",
            "details": clean_output,
        })
    except Exception as e:
        results.append({
            "test": "ProspectOutputValidator fallback behavior",
            "status": "FAIL",
            "details": str(e),
        })

    # --------------------------------------------------
    # 15. ProspectOutputValidator - truncation behavior
    # --------------------------------------------------
    try:
        output_validator = ProspectOutputValidator()
        long_text = "A" * 3000
        long_subject = "B" * 400
        clean_output = output_validator.validate_all(
            summary=long_text,
            angle=long_text,
            subject=long_subject,
            draft=long_text * 5,
        )
        results.append({
            "test": "ProspectOutputValidator truncation behavior",
            "status": "PASS",
            "details": {
                "summary_len": len(clean_output["business_summary"]),
                "angle_len": len(clean_output["outreach_angle"]),
                "subject_len": len(clean_output["email_subject"]),
                "draft_len": len(clean_output["email_draft"]),
            },
        })
    except Exception as e:
        results.append({
            "test": "ProspectOutputValidator truncation behavior",
            "status": "FAIL",
            "details": str(e),
        })

    return dict(results=results)



def test_models():
    results = []

    # Génération d'un UUID unique pour éviter de bloquer sur la contrainte UNIQUE
    test_uuid = str(uuid.uuid4())

    # --- 1. PROSPECT RUN ---
    ret = db.prospect_run.validate_and_insert(
        run_uuid=test_uuid,
        niche="dentists",
        city="Paris",
        offer="website redesign",
        status="idle",
        payment_status="pending",
    )
    if ret.get('errors'):  # CORRECTION ICI
        results.append(f"prospect_run validation failed: {ret.get('errors')}")
        return dict(results=results)
    run_id = ret.get('id') # CORRECTION ICI
    results.append(f"prospect_run inserted: {run_id}")

    # --- 2. PROSPECT ---
    ret = db.prospect.validate_and_insert(
        run_id=run_id,
        company_name="Cabinet Dentaire Paris Centre",
        domain="https://example.com",
        city="Paris",
        qualification_status="uncertain",
        render_order=0,
    )
    if ret.get('errors'):
        results.append(f"prospect validation failed: {ret.get('errors')}")
        return dict(results=results)
    prospect_id = ret.get('id')
    results.append(f"prospect inserted: {prospect_id}")

    # --- 3. SOURCE PAGE ---
    ret = db.prospect_source_page.validate_and_insert(
        prospect_id=prospect_id,
        url="https://example.com",
        page_type="homepage",
        loaded=True,
        http_status=200,
        extracted_text="Welcome to our dental clinic in Paris. Contact us at hello@example.com",
    )
    if ret.get('errors'):
        results.append(f"prospect_source_page validation failed: {ret.get('errors')}")
        return dict(results=results)
    source_id = ret.get('id')
    results.append(f"prospect_source_page inserted: {source_id}")

    # --- 4. CONTACT ---
    ret = db.prospect_contact.validate_and_insert(
        prospect_id=prospect_id,
        contact_type="email",
        value="hello@example.com",
        source_url="https://example.com/contact",
        confidence=0.9,
        is_primary=True,
    )
    if ret.get('errors'):
        results.append(f"prospect_contact validation failed: {ret.get('errors')}")
        return dict(results=results)
    contact_id = ret.get('id')
    results.append(f"prospect_contact inserted: {contact_id}")

    # --- 5. SIGNAL ---
    ret = db.prospect_signal.validate_and_insert(
        prospect_id=prospect_id,
        signal_type="criterion_match",
        signal_value="dentist",
        polarity="positive",
        reason="The site clearly indicates a dental clinic.",
    )
    if ret.get('errors'):
        results.append(f"prospect_signal validation failed: {ret.get('errors')}")
        return dict(results=results)
    signal_id = ret.get('id')
    results.append(f"prospect_signal inserted: {signal_id}")

    # --- 6. ARTIFACT ---
    ret = db.prospect_artifact.validate_and_insert(
        prospect_id=prospect_id,
        business_summary="Dental clinic based in Paris.",
        outreach_angle="Their website could be improved for local conversion.",
        email_subject="Quick idea for your dental clinic website",
        email_draft="Hi, I noticed your clinic website and had a quick idea to improve conversions.",
    )
    if ret.get('errors'):
        results.append(f"prospect_artifact validation failed: {ret.get('errors')}")
        return dict(results=results)
    artifact_id = ret.get('id')
    results.append(f"prospect_artifact inserted: {artifact_id}")

    db.commit()

    # --- VERIFICATION LECTURE ---
    run = db.prospect_run(run_id)
    prospects = db(db.prospect.run_id == run_id).select()
    contacts = db(db.prospect_contact.prospect_id == prospect_id).select()
    signals = db(db.prospect_signal.prospect_id == prospect_id).select()
    artifact = db(db.prospect_artifact.prospect_id == prospect_id).select().first()

    results.append(f"run fetched: {run.id if run else 'None'}")
    results.append(f"prospects count: {len(prospects)}")
    results.append(f"contacts count: {len(contacts)}")
    results.append(f"signals count: {len(signals)}")
    results.append(f"artifact exists: {artifact is not None}")

    return dict(results=results)

def test_models_invalid():
    results = []

    # Test 1 : Niche vide (Doit échouer à cause de IS_NOT_EMPTY)
    ret = db.prospect_run.validate_and_insert(
        run_uuid="bad-run-001",
        niche="",
        city="Paris",
        offer="website redesign",
    )
    if ret.get('errors'):
        results.append(f"expected failure for empty niche: {ret.get('errors')}")
    else:
        results.append(f"unexpected success: {ret.get('id')}")

    # Test 2 : Faux ID de run (Doit échouer à cause de IS_IN_DB)
    ret = db.prospect.validate_and_insert(
        run_id=999999,
        company_name="Ghost Company",
        domain="https://ghost.example",
    )
    if ret.get('errors'):
        results.append(f"expected failure for invalid run_id: {ret.get('errors')}")
    else:
        results.append(f"unexpected success: {ret.get('id')}")

    # Test 3 : Faux ID de prospect (Doit échouer à cause de IS_IN_DB)
    ret = db.prospect_artifact.validate_and_insert(
        prospect_id=999999,
        business_summary="Fake artifact",
    )
    if ret.get('errors'):
        results.append(f"expected failure for invalid prospect_id: {ret.get('errors')}")
    else:
        results.append(f"unexpected success: {ret.get('id')}")

    # Test 4 : Mauvais statut (Doit échouer à cause de IS_IN_SET)
    ret = db.prospect_run.validate_and_insert(
        run_uuid="bad-run-002",
        niche="dentists",
        city="Paris",
        offer="website redesign",
        status="wrong_status",
    )
    if ret.get('errors'):
        results.append(f"expected failure for invalid status: {ret.get('errors')}")
    else:
        results.append(f"unexpected success: {ret.get('id')}")

    return dict(results=results)

readsoningframe = "ReasoningFrame"

def lister_modeles_gemini():
    import urllib.request
    import json
    
    # On récupère la clé API directement depuis l'URL
    api_key = "AIzaSyBTXJPhqNK7u45x0R38xpBVDKHWzYadgdE"
    if not api_key:
        return "❌ Veuillez ajouter votre clé API dans l'URL. Exemple : /default/lister_modeles_gemini?api_key=AIza..."
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            # Construction d'un HTML basique pour lire facilement
            html_output = "<h2>✅ Modèles Gemini disponibles pour ta clé :</h2><ul>"
            
            for model in data.get("models", []):
                # On filtre pour ne garder que ceux qui génèrent du contenu
                if "generateContent" in model.get("supportedGenerationMethods", []):
                    nom_technique = model.get("name")
                    nom_affichage = model.get("displayName")
                    desc = model.get("description", "Pas de description")
                    
                    html_output += f"<li style='margin-bottom:15px; font-family:sans-serif;'>"
                    html_output += f"<strong style='color:blue;'>Nom technique : {nom_technique}</strong><br>"
                    html_output += f"<i>Affichage : {nom_affichage}</i><br>"
                    html_output += f"Description : {desc}"
                    html_output += f"</li><hr>"
                    
            html_output += "</ul>"
            
            # Retourne le HTML brut directement dans le navigateur
            return XML(html_output)
            
    except Exception as e:
        return f"<h3>❌ Erreur lors de l'appel à Google :</h3><p>{str(e)}</p>"




# ==========================================
# 1. INTAKE SAVE (Soumission du brief)
# ==========================================
@request.restful()
def api_intake_save():
    def GET(*args, **vars): raise HTTP(405, "Method Not Allowed")
    def PUT(*args, **vars): raise HTTP(405, "Method Not Allowed")
    def DELETE(*args, **vars): raise HTTP(405, "Method Not Allowed")

    def POST(*args, **vars):
        try:
            request.body.seek(0)
            body_raw = request.body.read()
            
            if not body_raw:
                response.status = 400
                return response.json({"ok": False, "error_code": "EMPTY_BODY", "message": "Request body is empty."})

            body_str = body_raw.decode("utf-8", errors="replace") if isinstance(body_raw, bytes) else str(body_raw)
            try:
                import json # S'assurer que json est bien importé
                payload = json.loads(body_str)
            except Exception:
                response.status = 400
                return response.json({"ok": False, "error_code": "INVALID_JSON", "message": "Body must be valid JSON."})

            # Identification du scope
            client_ip = request.client or request.env.remote_addr
            user_id = auth.user_id if ('auth' in globals() and auth) else None
            scope_key = f"u:{user_id}" if user_id else f"ip:{client_ip}"

            # Import du module service
            from applications.reasoningframe.modules import intake_service
            import importlib
            
            if request.is_local:
                importlib.reload(intake_service)

            # Traitement métier (Appel UNIQUE)
            result = intake_service.process_intake(
                db=db, payload=payload, scope_key=scope_key,
                user_agent=request.env.http_user_agent, client_ip=client_ip
            )

            # Si le backend refuse la sauvegarde (doublon, erreur métier, etc.), on s'arrête là
            if not result.get("ok"):
                response.status = 409 if result.get("error_code") == "CONCURRENT_REQUEST_PENDING" else 422
                return response.json(result)

            # ==========================================
            # APPEL À L'IA GEMINI (Le Cerveau)
            # ==========================================
            ai_contract = payload.get("ai_contract", {})
            api_key = ai_contract.get("api_key", "").strip()
            if not api_key:
                result["ai_status"] = "skipped_no_key"
            else:
                from applications.reasoningframe.modules import reasoning_service
                if request.is_local:
                    importlib.reload(reasoning_service)
                prompt_text = ai_contract.get("prompt_text", "")
                refs_dict = ai_contract.get("refs", {})
                auth_val = ai_contract.get("auth", 0)    
                # Le Ping Test !
                ai_result = reasoning_service.analyze_brief_with_gemini(api_key, prompt_text, refs_dict, auth_val)
                if ai_result.get("ok"):
                    result["ai_status"] = "success"
                    result["ai_data"] = ai_result.get("data")
                else:
                    # ==========================================
                    # 👇 PROTECTION LIFETIME : NETTOYAGE DE LA DB 👇
                    # ==========================================
                    # 1. On tente d'annuler la transaction en cours
                    db.rollback() 
                    
                    # 2. Sécurité supplémentaire : Si intake_service a déjà "commit", 
                    
                    # ==========================================

                    result["ai_status"] = "error"
                    result["ai_message"] = ai_result.get("message")
                    result["ai_error_code"] = ai_result.get("error_code")
            # ==========================================

            # Succès total
            response.status = 200
            return response.json(result)

        except Exception as e:
            db.rollback()
            import traceback
            print("CRITICAL INTAKE ERROR:\n", traceback.format_exc())
            response.status = 500
            return response.json({"ok": False, "error_code": "INTERNAL_ERROR", "message": f"Server Error: {str(e)}"})

    return locals()

# ==========================================
# 2. PIN TOGGLE (Épingler/Désépingler)
# ==========================================
@request.restful()
def api_pin_toggle():
    def POST(*args, **vars):
        try:
            request.body.seek(0)
            payload = json.loads(request.body.read().decode("utf-8"))
            hid = int(payload.get("history_item_id"))

            u_id = auth.user.id if (auth and auth.user) else None
            client_ip = request.client or request.env.remote_addr
            scope_key = f"u:{u_id}" if u_id else f"ip:{client_ip}"

            # Vérification de l'existence de l'item d'historique
            h, s = db.intake_history_item, db.intake_session
            owned = db((h.id == hid) & (h.session_id == s.id) & (s.scope_key == scope_key)).select(h.id).first()
            
            if not owned:
                return response.json({"ok": False, "error_code": "NOT_FOUND"})

            # Toggle logic
            q = (db.intake_pin.scope_key == scope_key) & (db.intake_pin.history_item_id == hid)
            existing = db(q).select().first()

            if existing:
                db(q).delete()
                action = "unpinned"
            else:
                fields = dict(scope_key=scope_key, history_item_id=hid)
                if u_id:
                    fields['created_by'] = u_id
                
                db.intake_pin.created_by.writable = True    
                res = db.intake_pin.validate_and_insert(**fields)
                db.intake_pin.created_by.writable = False
                
                if res.get("errors"):
                    db.rollback()
                    return response.json({"ok": False, "error_code": "PIN_DB_ERROR", "details": res.get("errors")})
                
                action = "pinned"

            db.commit()
            return response.json({"ok": True, "action": action, "history_item_id": hid})

        except Exception as e:
            db.rollback()
            import traceback
            print(f"CRASH PIN:\n{traceback.format_exc()}")
            return response.json({"ok": False, "message": str(e)})
            
    return locals()


# ==========================================
# 3. SIDEBAR LOAD (Chargement Initial)
# ==========================================
@request.restful()
def api_sidebar_load():
    def POST(*args, **vars): raise HTTP(405, "Method Not Allowed")
    def PUT(*args, **vars): raise HTTP(405, "Method Not Allowed")
    def DELETE(*args, **vars): raise HTTP(405, "Method Not Allowed")

    def GET(*args, **vars):
        try:
            client_ip = request.client or request.env.remote_addr
            user_id = auth.user.id if ('auth' in globals() and auth and auth.user) else None
            scope_key = f"u:{user_id}" if user_id else f"ip:{client_ip}"

            # 1. Récupération des Pins
            pins = db(db.intake_pin.scope_key == scope_key).select(
                db.intake_pin.history_item_id, 
                orderby=db.intake_pin.position | ~db.intake_pin.created_on
            )
            pinned_ids = [p.history_item_id for p in pins]

            # 2. Récupération de l'Historique
            h, s, r = db.intake_history_item, db.intake_session, db.intake_reference
            
            # Limité à 30 items pour ne pas faire exploser la RAM si les images sont lourdes
            rows = db((h.session_id == s.id) & (s.scope_key == scope_key)).select(
                h.id, h.title, h.intent, h.ts_ms, s.prompt_text, r.file_b64,
                left=r.on(h.thumb_ref_id == r.id),
                orderby=~h.created_on, limitby=(0, 30) 
            )

            history_items = []
            for row in rows:
                # Si l'image a été purgée par le "Lazy Pruning" (24h TTL), row.intake_reference.file_b64 vaudra None.
                # Brython affichera le "placeholder" proprement.
                thumb_data = row.intake_reference.file_b64 if row.intake_reference else None
                
                history_items.append({
                    "id": row.intake_history_item.id,
                    "title": row.intake_history_item.title,
                    "intent": row.intake_history_item.intent,
                    "ts_ms": row.intake_history_item.ts_ms,
                    "brief": row.intake_session.prompt_text,
                    "thumb_b64": thumb_data
                })
            
            history_items.reverse()

            return response.json({"ok": True, "pinned_ids": pinned_ids, "history_items": history_items})
            
        except Exception as e:
            import traceback
            print("CRITICAL SIDEBAR LOAD ERROR:\n", traceback.format_exc())
            return response.json({"ok": False, "pinned_ids": [], "history_items": []})

    return locals()


# ==========================================
# 4. HISTORY DELETE (Corbeille / Libérer de l'espace)
# ==========================================
@request.restful()
def api_history_delete():
    def POST(*args, **vars):
        try:
            request.body.seek(0)
            payload = json.loads(request.body.read().decode("utf-8"))
            hid = int(payload.get("history_item_id"))

            u_id = auth.user.id if ('auth' in globals() and auth and auth.user) else None
            client_ip = request.client or request.env.remote_addr
            scope_key = f"u:{u_id}" if u_id else f"ip:{client_ip}"

            # Vérifier l'appartenance
            h = db.intake_history_item
            s = db.intake_session
            item = db((h.id == hid) & (h.session_id == s.id) & (s.scope_key == scope_key)).select(s.id).first()
            
            if not item:
                return response.json({"ok": False, "error_code": "NOT_FOUND", "message": "Item not found or unauthorized."})

            # Suppression de la Session Mère (Cascade = efface refs + pins + history_item)
            db(db.intake_session.id == item.id).delete()
            db.commit()

            return response.json({"ok": True, "message": "Item deleted successfully."})

        except Exception as e:
            db.rollback()
            import traceback
            print(f"CRASH DELETE:\n{traceback.format_exc()}")
            return response.json({"ok": False, "message": str(e)})
            
    return locals()



def index():
    return dict()


def login():
    next_url = request.vars._next or session.get('oauth_next') or URL('default', 'dashboard')
    google_url = URL('default', 'google_begin', vars={'_next': next_url}) 
    return dict(google_url=google_url)


def google_redirect_uri():
    # => AJOUTE EXACTEMENT cette URL dans la console Google (Authorized redirect URIs)
    return URL('default', 'google_callback', scheme=True, host=True)


def google_begin():
    from urllib.parse import urlencode
    import uuid
    GOOGLE_CLIENT_ID = configuration.get('google.client_id')
    GOOGLE_CLIENT_SECRET = configuration.get('google.client_secret')
    """
    Démarre l’autorisation Google et envoie l’utilisateur chez Google.
    Tu peux appeler ce endpoint depuis ton bouton 'Continuer avec Google'.
    """
    state = str(uuid.uuid4())
    session.oauth_state = state

    # Où rediriger après login ? (optionnel)
    _next = request.vars.get('_next')
    if _next:
        session.oauth_next = _next

    params = dict(
        client_id=GOOGLE_CLIENT_ID,
        response_type='code',
        scope=GOOGLE_SCOPE,
        redirect_uri=google_redirect_uri(),
        include_granted_scopes='true',
        access_type='online',         # ou 'offline' si tu veux un refresh_token
        state=state,
        prompt='consent'              # optionnel
    )
    redirect(GOOGLE_AUTH_URL + '?' + urlencode(params))


def google_callback():
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode
    import json
    import logging
    GOOGLE_CLIENT_ID = configuration.get('google.client_id')
    GOOGLE_CLIENT_SECRET = configuration.get('google.client_secret')
    """
    Redirect URI autorisée (Google renvoie ici ?code&state ou ?error).
    Échange le code, récupère /userinfo, connecte/crée l’utilisateur,
    puis redirige vers _next (ou dashboard par défaut).
    """
    logger = logging.getLogger("web2py.app.yourfirstship")
    # 1) Erreur utilisateur (annule)
    if request.vars.get('error'):
        session.flash = 'Google sign-in cancelled.'
        return redirect(URL('default', 'login'))

    # 2) Anti-CSRF state
    if not session.get('oauth_state') or request.vars.get('state') != session.oauth_state:
        session.flash = 'Invalid state token.'
        return redirect(URL('default', 'login'))

    # 3) Code présent ?
    code = request.vars.get('code')
    if not code:
        session.flash = 'Authorization code missing.'
        return redirect(URL('default','login'))

    # 4) Échange code -> token
    data = dict(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        code=code,
        grant_type='authorization_code',
        redirect_uri=google_redirect_uri(),   # DOIT être identique à celle utilisée à l’aller
    )
    body = urlencode(data).encode('utf-8')
    try:
        resp = urlopen(Request(GOOGLE_TOKEN_URL,
                               data=body,
                               headers={'Content-Type':'application/x-www-form-urlencoded'}),
                       timeout=10)
        token_payload = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.error('Token exchange failed: %s', e)
        session.flash = 'Token exchange failed.'
        return redirect(URL('default', 'login'))

    access_token = token_payload.get('access_token')
    if not access_token:
        session.flash = 'Access token missing.'
        return redirect(URL('default','login'))

    session.token = access_token  # si tu veux le réutiliser ailleurs

    # 5) /userinfo
    try:
        uresp = urlopen(Request(GOOGLE_USERINFO_URL,
                                headers={'Authorization': 'Bearer %s' % access_token}),
                        timeout=10)
        data = json.loads(uresp.read().decode('utf-8'))
    except Exception as e:
        logger.error('Userinfo failed: %s', e)
        session.flash = 'Unable to read Google profile.'
        return redirect(URL('default','login'))

    profile = dict(
       first_name = data.get('given_name', ''),
        last_name  = data.get('family_name', ''),
        email      = data.get('email'),
        username   = data.get('email'), # On utilise l'email comme username
        
        # --- CHAMPS CRITIQUES ---
        google_id  = data.get('sub'),   # L'ID unique immuable de Google
        avatar_url = data.get('picture', ''), # On récupère la photo
    )

    # 7) Création/connexion utilisateur web2py
    user = auth.get_or_create_user(profile)   # crée si inexistant
    if not user:
        session.flash = 'Unable to create or log in user.'
        return redirect(URL('default', 'login'))
    
    auth.login_user(user)
    # 8) Redirection finale
    _next = session.pop('oauth_next', None) or request.vars.get('_next') or URL('default','dashboard')
    redirect(_next)



def logout():
    return dict(form=auth.logout())


# ---- API (example) -----
@auth.requires_login()
def api_get_user_email():
    if not request.env.request_method == 'GET': raise HTTP(403)
    return response.json({'status':'success', 'email':auth.user.email})

# ---- Smart Grid (example) -----
@auth.requires_membership('admin') # can only be accessed by members of admin groupd
def grid():
    response.view = 'generic.html' # use a generic view
    tablename = request.args(0)
    if not tablename in db.tables: raise HTTP(403)
    grid = SQLFORM.smartgrid(db[tablename], args=[tablename], deletable=False, editable=False)
    return dict(grid=grid)

# ---- Embedded wiki (example) ----
def wiki():
    auth.wikimenu() # add the wiki to the menu
    return auth.wiki() 

# ---- Action for login/register/etc (required for auth) -----
def user():
    """
    exposes:
    http://..../[app]/default/user/login
    http://..../[app]/default/user/logout
    http://..../[app]/default/user/register
    http://..../[app]/default/user/profile
    http://..../[app]/default/user/retrieve_password
    http://..../[app]/default/user/change_password
    http://..../[app]/default/user/bulk_register
    use @auth.requires_login()
        @auth.requires_membership('group name')
        @auth.requires_permission('read','table name',record_id)
    to decorate functions that need access control
    also notice there is http://..../[app]/appadmin/manage/auth to allow administrator to manage users
    """
    return dict(form=auth())

# ---- action to server uploaded static content (required) ---
@cache.action()
def download():
    """
    allows downloading of uploaded files
    http://..../[app]/default/download/[filename]
    """
    return response.download(request, db)
