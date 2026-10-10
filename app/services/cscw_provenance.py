"""PROV-O projection of the persisted CSCW provenance events (SDD2 §10.5).

The transactional ``provenance_events`` table stays the source of truth; this
module only *reads* it and builds a ``ProvDocument`` for technical audit.

Privacy contract (SDD2 §10.2/§10.5): the projection never emits message
content, investigation titles, names, e-mails, CRM, SHORTIDs, revocation
reasons, filter dates or notification payloads as literals. Human agents are
identified by a keyed-HMAC pseudonymous IRI of the account id; literals are
limited to activity types, domain roles, lifecycle statuses and version/
sequence numbers. Even so, who-talked-to-whom is clinical metadata, so the
output must only be written to protected, non-public locations (see
``scripts/export_cscw_provenance.py``).

Mapping ``activity_type`` -> PROV-O (documented in README):

=========================================== ==============================================================
activity_type                               projection
=========================================== ==============================================================
AssociationRequested                        Activity; generates link v1; Agent=Patient
AssociationConfirmed/Rejected/              Activity; used link v(n); generates v(n+1) wasRevisionOf v(n);
AssociationRequestCancelled/Revoked         v(n+1) wasAttributedTo actor
DemoAssociationProvisioned                  Activity; SoftwareAgent importer; used data source; generates v1
InvestigationOpened                         Activity; used link version in force (+ daily indicator when
                                            opened from an atypical day); generates investigation v1;
                                            mygv:underAssociation / mygv:investigatesAtypicalDay
InvestigationMessageAdded                   Activity; generates message (wasAttributedTo author); when the
                                            event carries a version, used inv v(n-1) -> generates v(n);
                                            wasInformedBy the causing activity (opening/closing)
InvestigationReadAdvanced                   Activity; used investigation; generates read-position marker
                                            (wasRevisionOf previous marker)
InvestigationClosed                         Activity; used inv v(n) -> generates v(n+1)
InvestigationClosedByAssociationRevocation  Activity; SoftwareAgent; used inv v(n) -> v(n+1);
                                            wasInformedBy AssociationRevoked
AtypicalDayInvestigationPromptCreated       Activity; SoftwareAgent analytics; used daily indicator;
                                            generates prompt (mygv:promptsForAtypicalDay)
AtypicalDayInvestigationPromptDeferred      Activity; Agent=Patient; used prompt
NotificationCreated                         Activity; SoftwareAgent; generates notification;
                                            wasInformedBy the causal activity
NotificationRead                            Activity; Agent=recipient; used notification
AtypicalDayDetailViewed                     Activity; Agent=actor; used patient record (no dates)
PatientDetailFilterApplied                  Activity; Agent=actor; used patient record (no dates)
=========================================== ==============================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from prov.model import PROV, ProvDocument
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import _lookup_hmac
from app.models.entities import (
    AtypicalDayPrompt, Doctor, Investigation, Notification, Patient, PatientDoctorLink, ProvenanceEvent,
)

# Terms are declared in ontology/mygv-dpo-extension.owl.ttl; the vocabulary IRI
# is the ontology's, not a deployment setting, so exported terms always resolve.
MYGV_NAMESPACE = "https://w3id.org/myglico/vocab/"
# Same namespace and software-agent IRIs as app/services/provenance.py.
EXECUTION_NAMESPACE = "https://myglico.local/execution/"
IMPORTER_AGENT = "ex:myglico-importer"
ANALYTICS_AGENT = "ex:myglico-analytics"
COLLABORATION_AGENT = "ex:myglico-collaboration-service"

LINK_ACTIVITIES = {
    "AssociationRequested", "AssociationConfirmed", "AssociationRejected",
    "AssociationRequestCancelled", "AssociationRevoked", "DemoAssociationProvisioned",
}
INVESTIGATION_ACTIVITIES = {
    "InvestigationOpened", "InvestigationMessageAdded", "InvestigationReadAdvanced",
    "InvestigationClosed", "InvestigationClosedByAssociationRevocation",
}
PROMPT_ACTIVITIES = {"AtypicalDayInvestigationPromptCreated", "AtypicalDayInvestigationPromptDeferred"}
NOTIFICATION_ACTIVITIES = {"NotificationCreated", "NotificationRead"}
ACCESS_ACTIVITIES = {"AtypicalDayDetailViewed", "PatientDetailFilterApplied"}
CSCW_ACTIVITY_TYPES = frozenset(
    LINK_ACTIVITIES | INVESTIGATION_ACTIVITIES | PROMPT_ACTIVITIES | NOTIFICATION_ACTIVITIES | ACCESS_ACTIVITIES
)


def agent_pseudonym(account_id: str) -> str:
    """Keyed, stable token for a user account: without the lookup key, an
    exported agent IRI cannot be confirmed against a known account id."""
    return _lookup_hmac("cscw_prov_agent", account_id)[:32]


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@dataclass
class _Projector:
    db: Session
    document: ProvDocument
    _patient_cache: dict[str, str | None] = field(default_factory=dict)
    _role_cache: dict[str, str | None] = field(default_factory=dict)
    _declared: set[str] = field(default_factory=set)
    _relations: set[tuple[str, str, str]] = field(default_factory=set)

    # -- IRIs -------------------------------------------------------------
    @staticmethod
    def activity_id(event_id: str) -> str:
        return f"myg:prov-event/{event_id}"

    @staticmethod
    def link_id(link_id: str, version: int | None = None) -> str:
        base = f"myg:patient-doctor-link/{link_id}"
        return base if version is None else f"{base}/v{version}"

    @staticmethod
    def investigation_id(investigation_id: str, version: int | None = None) -> str:
        base = f"myg:investigation/{investigation_id}"
        return base if version is None else f"{base}/v{version}"

    # -- declarations (idempotent) ------------------------------------------
    def _entity(self, identifier: str, attributes: dict | None = None) -> str:
        if identifier not in self._declared:
            self.document.entity(identifier, attributes or {})
            self._declared.add(identifier)
        return identifier

    def _versioned(self, general: str, version: int, entity_class: str, status: str | None = None) -> str:
        self._entity(general, {"prov:type": self.document.valid_qualified_name(entity_class)})
        identifier = f"{general}/v{version}"
        if identifier not in self._declared:
            attributes: dict = {
                "prov:type": self.document.valid_qualified_name(entity_class),
                "mygv:entityVersion": version,
            }
            if status:
                attributes["mygv:lifecycleStatus"] = status
            self._entity(identifier, attributes)
            self.document.specializationOf(identifier, general)
        return identifier

    def _revision(self, general: str, before: int | None, after: int | None, entity_class: str,
                  activity: str, agent: str | None, status: str | None = None, *, attribute: bool = True) -> None:
        if after is None:
            return
        generated = self._versioned(general, after, entity_class, status)
        self.document.wasGeneratedBy(generated, activity)
        if before:
            previous = self._versioned(general, before, entity_class)
            self.document.used(activity, previous)
            self.document.wasRevisionOf(generated, previous)
        if agent and attribute:
            self.document.wasAttributedTo(generated, agent)

    def human_agent(self, account_id: str) -> str:
        identifier = f"myg:agent/{agent_pseudonym(account_id)}"
        if identifier not in self._declared:
            attributes = {}
            role = self._account_role(account_id)
            if role:
                attributes["mygv:domainRole"] = role
            self.document.agent(identifier, attributes)
            self._declared.add(identifier)
        return identifier

    def software_agent(self, identifier: str) -> str:
        if identifier not in self._declared:
            self.document.agent(identifier, {"prov:type": PROV["SoftwareAgent"]})
            self._declared.add(identifier)
        return identifier

    def _account_role(self, account_id: str) -> str | None:
        if account_id not in self._role_cache:
            role = None
            if self.db.scalar(select(Patient.id).where(Patient.user_account_id == account_id)):
                role = "patient"
            elif self.db.scalar(select(Doctor.id).where(Doctor.user_account_id == account_id)):
                role = "doctor"
            self._role_cache[account_id] = role
        return self._role_cache[account_id]

    # -- authorization scope ---------------------------------------------
    def patient_of(self, event: ProvenanceEvent, depth: int = 0) -> str | None:
        if event.id in self._patient_cache:
            return self._patient_cache[event.id]
        patient_id: str | None = None
        if event.entity_type == "patient_doctor_link":
            patient_id = self.db.scalar(select(PatientDoctorLink.patient_id).where(PatientDoctorLink.id == event.entity_id))
        elif event.entity_type == "investigation":
            patient_id = self.db.scalar(select(Investigation.patient_id).where(Investigation.id == event.entity_id))
        elif event.entity_type == "atypical_day_prompt":
            patient_id = self.db.scalar(select(AtypicalDayPrompt.patient_id).where(AtypicalDayPrompt.id == event.entity_id))
        elif event.entity_type == "patient":
            patient_id = event.entity_id
        elif event.entity_type == "notification" and depth < 3:
            cause_id = self.db.scalar(select(Notification.causation_event_id).where(Notification.id == event.entity_id))
            cause = self.db.get(ProvenanceEvent, cause_id) if cause_id else None
            patient_id = self.patient_of(cause, depth + 1) if cause is not None else None
        self._patient_cache[event.id] = patient_id
        return patient_id

    def _link_version_at(self, link_id: str, at: datetime) -> int | None:
        rows = self.db.scalars(select(ProvenanceEvent).where(
            ProvenanceEvent.entity_type == "patient_doctor_link",
            ProvenanceEvent.entity_id == link_id,
            ProvenanceEvent.activity_type.in_(LINK_ACTIVITIES),
            ProvenanceEvent.occurred_at <= at,
        ).order_by(ProvenanceEvent.occurred_at.desc(), ProvenanceEvent.id.desc()))
        for row in rows:
            if row.activity_type == "DemoAssociationProvisioned":
                return 1
            version = _int((row.metadata_json or {}).get("after_version"))
            if version is not None:
                return version
        return None

    # -- projection -------------------------------------------------------
    def project(self, event: ProvenanceEvent) -> None:
        meta = event.metadata_json or {}
        occurred = _utc(event.occurred_at)
        activity = self.activity_id(event.id)
        self.document.activity(activity, occurred, occurred, {
            "prov:type": self.document.valid_qualified_name("mygv:CollaborationActivity"),
            "mygv:activityType": event.activity_type,
        })
        self._declared.add(activity)

        agent: str | None = None
        if event.source_type == "software-agent":
            if event.activity_type == "DemoAssociationProvisioned":
                agent = self.software_agent(IMPORTER_AGENT)
            elif event.activity_type == "AtypicalDayInvestigationPromptCreated":
                agent = self.software_agent(ANALYTICS_AGENT)
            else:
                agent = self.software_agent(COLLABORATION_AGENT)
        elif event.actor_user_id:
            agent = self.human_agent(event.actor_user_id)
        if agent:
            self.document.wasAssociatedWith(activity, agent)

        causation = meta.get("causation_event_id")
        if event.activity_type == "NotificationCreated" and not causation:
            causation = event.source_id
        if causation:
            self.document.wasInformedBy(activity, self.activity_id(str(causation)))

        handler = getattr(self, f"_on_{event.activity_type}", None)
        if handler is not None:
            handler(event, meta, activity, agent)

    # Association lifecycle
    def _on_link(self, event, meta, activity, agent) -> None:
        general = self.link_id(event.entity_id)
        self._revision(general, _int(meta.get("before_version")), _int(meta.get("after_version")),
                       "mygv:PatientDoctorAssociation", activity, agent, meta.get("to_status"))

    _on_AssociationRequested = _on_link
    _on_AssociationConfirmed = _on_link
    _on_AssociationRejected = _on_link
    _on_AssociationRequestCancelled = _on_link
    _on_AssociationRevoked = _on_link

    def _on_DemoAssociationProvisioned(self, event, meta, activity, agent) -> None:
        if event.source_id:
            source = self._entity(f"ex:data-source-{event.source_id}", {
                "prov:type": self.document.valid_qualified_name("mygv:DataSource"),
            })
            self.document.used(activity, source)
        self._revision(self.link_id(event.entity_id), None, 1, "mygv:PatientDoctorAssociation",
                       activity, agent, "ACTIVE")

    # Investigations
    def _investigation(self, investigation_id: str) -> str:
        return self._entity(self.investigation_id(investigation_id), {
            "prov:type": self.document.valid_qualified_name("mygv:Investigation"),
        })

    def _on_InvestigationOpened(self, event, meta, activity, agent) -> None:
        general = self._investigation(event.entity_id)
        association_id = meta.get("association_id")
        if association_id:
            link_general = self._entity(self.link_id(association_id), {
                "prov:type": self.document.valid_qualified_name("mygv:PatientDoctorAssociation"),
            })
            version = self._link_version_at(association_id, event.occurred_at)
            if version is not None:
                self.document.used(activity, self._versioned(link_general, version, "mygv:PatientDoctorAssociation"))
            else:
                self.document.used(activity, link_general)
            self._domain_relation(general, "mygv:underAssociation", link_general)
        indicator_id = meta.get("atypical_day_event_id")
        if indicator_id:
            indicator = self._daily_indicator(indicator_id)
            self.document.used(activity, indicator)
            self._domain_relation(general, "mygv:investigatesAtypicalDay", indicator)
        self._revision(general, None, _int(meta.get("version")) or 1, "mygv:Investigation",
                       activity, agent, "OPEN")

    def _on_InvestigationMessageAdded(self, event, meta, activity, agent) -> None:
        general = self._investigation(event.entity_id)
        message_id = meta.get("message_id")
        if message_id:
            attributes: dict = {"prov:type": self.document.valid_qualified_name("mygv:InvestigationMessage")}
            sequence = _int(meta.get("sequence"))
            if sequence is not None:
                attributes["mygv:messageSequence"] = sequence
            message = self._entity(f"myg:investigation-message/{message_id}", attributes)
            self._domain_relation(message, "mygv:partOfInvestigation", general)
            self.document.wasGeneratedBy(message, activity)
            if agent:
                self.document.wasAttributedTo(message, agent)
        after = _int(meta.get("version"))
        if after is not None and after > 1:
            self._revision(general, after - 1, after, "mygv:Investigation", activity, agent, "OPEN",
                           attribute=False)

    def _on_InvestigationReadAdvanced(self, event, meta, activity, agent) -> None:
        general = self._investigation(event.entity_id)
        self.document.used(activity, general)
        role = str(meta.get("participant_role") or "unknown").lower()
        before = _int(meta.get("last_read_sequence_before")) or 0
        after = _int(meta.get("last_read_sequence_after"))
        if after is None:
            return
        marker_base = f"{general}/read-position/{role}"

        def marker(sequence: int) -> str:
            identifier = self._entity(f"{marker_base}/{sequence}", {
                "prov:type": self.document.valid_qualified_name("mygv:InvestigationReadPosition"),
                "mygv:readSequence": sequence,
            })
            self._domain_relation(identifier, "mygv:partOfInvestigation", general)
            return identifier

        current = marker(after)
        self.document.wasGeneratedBy(current, activity)
        if agent:
            self.document.wasAttributedTo(current, agent)
        if before > 0:
            self.document.wasRevisionOf(current, marker(before))

    def _on_InvestigationClosed(self, event, meta, activity, agent) -> None:
        general = self._investigation(event.entity_id)
        self._revision(general, _int(meta.get("before_version")), _int(meta.get("after_version")),
                       "mygv:Investigation", activity, agent, "CLOSED")

    _on_InvestigationClosedByAssociationRevocation = _on_InvestigationClosed

    # Atypical-day prompts
    def _daily_indicator(self, indicator_id: str) -> str:
        return self._entity(f"myg:daily-indicator/{indicator_id}", {
            "prov:type": self.document.valid_qualified_name("mygv:DailyIndicator"),
        })

    def _prompt(self, prompt_id: str) -> str:
        return self._entity(f"myg:atypical-day-prompt/{prompt_id}", {
            "prov:type": self.document.valid_qualified_name("mygv:AtypicalDayPrompt"),
        })

    def _on_AtypicalDayInvestigationPromptCreated(self, event, meta, activity, agent) -> None:
        prompt = self._prompt(event.entity_id)
        self.document.wasGeneratedBy(prompt, activity)
        indicator_id = meta.get("daily_indicator_id") or event.source_id
        if indicator_id:
            indicator = self._daily_indicator(indicator_id)
            self.document.used(activity, indicator)
            self._domain_relation(prompt, "mygv:promptsForAtypicalDay", indicator)

    def _on_AtypicalDayInvestigationPromptDeferred(self, event, meta, activity, agent) -> None:
        self.document.used(activity, self._prompt(event.entity_id))

    # Notifications
    def _notification(self, notification_id: str) -> str:
        return self._entity(f"myg:notification/{notification_id}", {
            "prov:type": self.document.valid_qualified_name("mygv:Notification"),
        })

    def _on_NotificationCreated(self, event, meta, activity, agent) -> None:
        self.document.wasGeneratedBy(self._notification(event.entity_id), activity)

    def _on_NotificationRead(self, event, meta, activity, agent) -> None:
        self.document.used(activity, self._notification(event.entity_id))

    # Authorized access to clinical results (dates/criteria deliberately omitted)
    def _on_access(self, event, meta, activity, agent) -> None:
        patient = self._entity(f"myg:patient/{event.entity_id}", {
            "prov:type": self.document.valid_qualified_name("mygv:Patient"),
        })
        self.document.used(activity, patient)

    _on_AtypicalDayDetailViewed = _on_access
    _on_PatientDetailFilterApplied = _on_access

    def _domain_relation(self, subject: str, predicate: str, target: str) -> None:
        key = (subject, predicate, target)
        if key in self._relations:
            return
        self._relations.add(key)
        record = self.document.get_record(subject)
        if record:
            record[0].add_attributes({predicate: self.document.valid_qualified_name(target)})


def _new_document() -> ProvDocument:
    settings = get_settings()
    document = ProvDocument()
    document.add_namespace("myg", settings.semantic_base_uri)
    document.add_namespace("mygv", MYGV_NAMESPACE)
    document.add_namespace("ex", EXECUTION_NAMESPACE)
    return document


def select_cscw_events(
    db: Session, *, start: datetime | None = None, end: datetime | None = None,
) -> list[ProvenanceEvent]:
    query = select(ProvenanceEvent).where(ProvenanceEvent.activity_type.in_(sorted(CSCW_ACTIVITY_TYPES)))
    if start is not None:
        query = query.where(ProvenanceEvent.occurred_at >= start)
    if end is not None:
        query = query.where(ProvenanceEvent.occurred_at < end)
    return list(db.scalars(query.order_by(ProvenanceEvent.occurred_at, ProvenanceEvent.id)))


def build_cscw_prov_document(
    db: Session, *, patient_id: str | None = None,
    start: datetime | None = None, end: datetime | None = None,
    events: Iterable[ProvenanceEvent] | None = None,
) -> ProvDocument:
    """Project CSCW ``ProvenanceEvent`` rows into PROV-O.

    ``patient_id`` scopes the projection to the events of one patient (the
    same scope the patient's own history endpoint grants); ``start``/``end``
    are UTC bounds on ``occurred_at`` (end exclusive).
    """
    document = _new_document()
    projector = _Projector(db=db, document=document)
    rows = list(events) if events is not None else select_cscw_events(db, start=start, end=end)
    for event in rows:
        if event.activity_type not in CSCW_ACTIVITY_TYPES:
            continue
        if patient_id is not None and projector.patient_of(event) != patient_id:
            continue
        projector.project(event)
    return document


def add_unqualified_shortcuts(turtle: str) -> str:
    """Add ``prov:wasRevisionOf`` shortcuts next to the qualified revisions.

    The ``prov`` library serializes revisions only as ``prov:qualifiedRevision``
    blank nodes; PROV-O defines both forms, and SPARQL consumers expect the
    direct property.
    """
    from rdflib import Graph, Namespace

    prov_ns = Namespace("http://www.w3.org/ns/prov#")
    graph = Graph()
    graph.parse(data=turtle, format="turtle")
    for subject, qualified in list(graph.subject_objects(prov_ns.qualifiedRevision)):
        for used in graph.objects(qualified, prov_ns.entity):
            graph.add((subject, prov_ns.wasRevisionOf, used))
    return graph.serialize(format="turtle")


def serialize_cscw_prov(document: ProvDocument) -> tuple[str, str]:
    """Return ``(prov_json, turtle)`` for ``document``."""
    json_text = document.serialize(format="json", indent=2)
    turtle = document.serialize(format="rdf", rdf_format="ttl")
    return json_text, add_unqualified_shortcuts(turtle)
