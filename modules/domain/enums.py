from enum import Enum


class RunStatus(str, Enum):
    IDLE = "idle"
    VALIDATING_INPUT = "validating_input"
    SEARCHING = "searching"
    INSPECTING = "inspecting"
    EXTRACTING_CONTACTS = "extracting_contacts"
    QUALIFYING = "qualifying"
    DRAFTING = "drafting"
    RENDERING = "rendering"
    LOCKED_PREVIEW = "locked_preview"
    UNLOCKED = "unlocked"
    EXPORTED = "exported"
    FAILED = "failed"


class QualificationStatus(str, Enum):
    QUALIFIED = "qualified"
    NOT_QUALIFIED = "not_qualified"
    UNCERTAIN = "uncertain"


class ContactType(str, Enum):
    EMAIL = "email"
    CONTACT_PAGE = "contact_page"
    PHONE = "phone"
    NONE = "none"


class SignalPolarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class SignalSourceKind(str, Enum):
    RULE = "rule"
    LLM = "llm"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourcePageType(str, Enum):
    HOMEPAGE = "homepage"
    CONTACT = "contact"
    OTHER = "other"


class PaymentStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


RUN_STATUS_VALUES = [e.value for e in RunStatus]
QUALIFICATION_STATUS_VALUES = [e.value for e in QualificationStatus]
CONTACT_TYPE_VALUES = [e.value for e in ContactType]
SIGNAL_POLARITY_VALUES = [e.value for e in SignalPolarity]
SIGNAL_SOURCE_KIND_VALUES = [e.value for e in SignalSourceKind]
CONFIDENCE_LEVEL_VALUES = [e.value for e in ConfidenceLevel]
SOURCE_PAGE_TYPE_VALUES = [e.value for e in SourcePageType]
PAYMENT_STATUS_VALUES = [e.value for e in PaymentStatus]