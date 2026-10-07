"""Persisted provenance: required events, actor kind, append-only integrity.

Covers the provenance side of CSCW-CA-04, CSCW-CA-05, CSCW-CA-12, CSCW-CA-28,
CSCW-CA-37 and CSCW-CA-43, plus the human-vs-SoftwareAgent distinction required
by PROMPT-ORCA.md ("testes de integração ... ator humano versus SoftwareAgent").
"""

from __future__ import annotations

from datetime import datetime, timedelta

from conftest import World

REQUIRED_EVENTS = (
    "AssociationRequested",
    "AssociationConfirmed",
    "AssociationRejected",
    "AssociationRequestCancelled",
    "AssociationRevoked",
    "DemoAssociationProvisioned",
    "InvestigationOpened",
    "InvestigationMessageAdded",
    "InvestigationReadAdvanced",
    "InvestigationClosed",
    "InvestigationClosedByAssociationRevocation",
    "AtypicalDayInvestigationPromptCreated",
    "AtypicalDayInvestigationPromptDeferred",
    "NotificationCreated",
    "NotificationRead",
)


def _provision_demo_link(world: World) -> str:
    """Run the importer's provisioning on a UCI-sourced patient created here (no network)."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import DataSource, Patient, PatientDoctorLink, PatientSourceLink
    from app.services.uci_importer import provision_demo_accounts

    with SessionLocal() as db:
        source = db.scalar(select(DataSource).where(DataSource.name == "UCI Diabetes", DataSource.version == "UCI-34"))
        if source is None:
            source = DataSource(name="UCI Diabetes", version="UCI-34", source_type="dataset")
            db.add(source)
            db.flush()
        patient = Patient(name="UCI provenance patient")
        db.add(patient)
        db.flush()
        code = f"it-{patient.id[:8]}"
        db.add(PatientSourceLink(patient_id=patient.id, data_source_id=source.id,
                                 external_patient_code=code, source_file=f"data-{code}"))
        db.commit()
        provision_demo_accounts(db)
        link_id = db.scalar(select(PatientDoctorLink.id).where(PatientDoctorLink.patient_id == patient.id))
        assert link_id is not None
        return link_id


def test_every_required_transition_persists_its_event(db_session, world: World):
    """Drive one full lifecycle and assert each mandatory event exists with the right aggregate."""
    patient, prompts = world.atypical_patient()
    doctor, rejecting, cancelled = world.doctor(), world.doctor(), world.doctor()

    link = world.request_link(patient, doctor)
    confirmed = doctor.client.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": 1}).json()["link"]
    rejected_link = world.request_link(patient, rejecting)
    assert rejecting.client.post(f"/api/doctor-links/{rejected_link['id']}/reject", json={"version": 1}).status_code == 200
    cancelled_link = world.request_link(patient, cancelled)
    assert patient.client.post(f"/api/doctor-links/{cancelled_link['id']}/cancel", json={"version": 1}).status_code == 200

    deferred = patient.client.post(f"/api/atypical-day-prompts/{prompts[0]['indicator_id']}/defer")
    assert deferred.status_code == 200
    investigation = world.open_investigation(patient, doctor, event_id=prompts[0]["indicator_id"])
    assert doctor.client.post(f"/api/investigations/{investigation['id']}/messages", json={"content": "r"}).status_code == 201
    assert patient.client.post(f"/api/investigations/{investigation['id']}/read", json={"up_to_sequence": 2}).status_code == 200
    closed = patient.client.post(f"/api/investigations/{investigation['id']}/close", json={"version": 2})
    assert closed.status_code == 200, closed.text
    still_open = world.open_investigation(patient, doctor)
    note = doctor.client.get("/api/notifications").json()["notifications"][0]
    assert doctor.client.post(f"/api/notifications/{note['id']}/read").status_code == 200
    assert patient.client.post(f"/api/doctor-links/{link['id']}/revoke",
                               json={"version": confirmed["version"]}).status_code == 200
    demo_link = _provision_demo_link(world)

    expected_entities = {
        "AssociationRequested": link["id"], "AssociationConfirmed": link["id"],
        "AssociationRejected": rejected_link["id"], "AssociationRequestCancelled": cancelled_link["id"],
        "AssociationRevoked": link["id"], "DemoAssociationProvisioned": demo_link,
        "InvestigationOpened": investigation["id"], "InvestigationMessageAdded": investigation["id"],
        "InvestigationReadAdvanced": investigation["id"], "InvestigationClosed": investigation["id"],
        "InvestigationClosedByAssociationRevocation": still_open["id"],
        "NotificationRead": note["id"],
    }
    for activity in REQUIRED_EVENTS:
        rows = world.events(activity, expected_entities.get(activity))
        assert rows, f"missing {activity}"
        for row in rows:
            assert row.occurred_at is not None and row.prov_json and row.prov_json.get("activity") == activity
    # Prompt events belong to this patient's prompts.
    prompt_events = [e for e in world.events("AtypicalDayInvestigationPromptCreated")
                     if (e.metadata_json or {}).get("patient_id") == patient.id]
    assert {e.metadata_json["daily_indicator_id"] for e in prompt_events} >= {prompts[0]["indicator_id"]}
    assert any((e.metadata_json or {}).get("daily_indicator_id") == prompts[0]["indicator_id"]
               for e in world.events("AtypicalDayInvestigationPromptDeferred"))
    # Versioned aggregates carry their version transition.
    revoke = world.events("AssociationRevoked", link["id"])[0]
    assert (revoke.metadata_json["before_version"], revoke.metadata_json["after_version"]) == (2, 3)
    auto_close = world.events("InvestigationClosedByAssociationRevocation", still_open["id"])[0]
    assert auto_close.metadata_json["causation_event_id"] == revoke.id


def test_cscw_ca_04_and_05_events_carry_correct_actor_authorship_and_version(db_session, world: World):
    """CSCW-CA-04/CSCW-CA-05: events record who acted, when and from which version."""
    patient = world.patient()
    confirming, rejecting, cancelled = world.doctor(), world.doctor(), world.doctor()
    patient_account = world.account_id(patient)

    cases = []
    start = datetime.utcnow() - timedelta(seconds=1)
    link = world.request_link(patient, confirming)
    assert confirming.client.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": 1}).status_code == 200
    cases.append(("AssociationConfirmed", link["id"], confirming, "PENDING", "ACTIVE"))
    link = world.request_link(patient, rejecting)
    assert rejecting.client.post(f"/api/doctor-links/{link['id']}/reject", json={"version": 1}).status_code == 200
    cases.append(("AssociationRejected", link["id"], rejecting, "PENDING", "REJECTED"))
    link = world.request_link(patient, cancelled)
    assert patient.client.post(f"/api/doctor-links/{link['id']}/cancel", json={"version": 1}).status_code == 200
    cases.append(("AssociationRequestCancelled", link["id"], patient, "PENDING", "CANCELLED"))
    end = datetime.utcnow() + timedelta(seconds=1)

    for activity, link_id, actor, from_status, to_status in cases:
        (event,) = world.events(activity, link_id)
        assert event.actor_user_id == world.account_id(actor)
        assert event.source_type == "user" and event.source_id == actor.id
        meta = event.metadata_json
        assert (meta["before_version"], meta["after_version"]) == (1, 2)
        assert (meta["from_status"], meta["to_status"]) == (from_status, to_status)
        assert meta["patient_id"] == patient.id
        assert start <= event.occurred_at <= end, "occurred_at must be server UTC time"
        (requested,) = world.events("AssociationRequested", link_id)
        assert requested.actor_user_id == patient_account and requested.metadata_json["after_version"] == 1
        assert requested.occurred_at <= event.occurred_at
    # A stale or foreign attempt leaves no success event.
    link = world.request_link(patient, world.doctor())
    assert confirming.client.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": 1}).status_code == 404
    assert world.events("AssociationConfirmed", link["id"]) == []


def test_human_actor_versus_software_agent_are_distinguishable(db_session, world: World):
    """Human actions vs importer/analytics SoftwareAgent are explicitly typed."""
    patient, prompts = world.atypical_patient()
    doctor = world.doctor()
    link = world.active_link(patient, doctor)
    demo_link = _provision_demo_link(world)

    human = world.events("AssociationConfirmed", link["id"])[0]
    importer = world.events("DemoAssociationProvisioned", demo_link)[0]
    prompt_events = [e for e in world.events("AtypicalDayInvestigationPromptCreated")
                     if (e.metadata_json or {}).get("patient_id") == patient.id]
    notification_events = world.events("NotificationCreated")

    assert human.source_type == "user" and human.actor_user_id == world.account_id(doctor)
    for machine in [importer, *prompt_events, *notification_events]:
        assert machine.source_type == "software-agent", machine.activity_type
        assert machine.actor_user_id is None, machine.activity_type
    assert importer.metadata_json.get("actor_kind") == "SoftwareImporter"
    assert world.events("AssociationConfirmed", demo_link) == []
    assert prompts and prompt_events


def test_cscw_ca_28_no_success_event_exists_for_a_failed_mutation(db_session, world: World):
    """CSCW-CA-28: a rolled-back mutation leaves no success event behind."""
    from app.models.entities import Investigation, PatientDoctorLink

    patient, doctor = world.patient(), world.doctor()
    link = world.active_link(patient, doctor)
    investigation = world.open_investigation(patient, doctor)
    # Fail the *last* write of the revoke unit (the cascaded investigation close event).
    with world.failing_insert("provenance_events",
                              "NEW.activity_type = 'InvestigationClosedByAssociationRevocation'"):
        failed = doctor.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": link["version"]})
    assert failed.status_code >= 500
    assert world.events("AssociationRevoked", link["id"]) == []
    assert world.events("InvestigationClosedByAssociationRevocation", investigation["id"]) == []
    db_session.expire_all()
    assert db_session.get(PatientDoctorLink, link["id"]).status == "ACTIVE"
    assert db_session.get(Investigation, investigation["id"]).status == "OPEN"
    # Same for a close: no InvestigationClosed without the CLOSED state, and vice versa.
    with world.failing_insert("notifications", "NEW.notification_type = 'investigation_closed'"):
        failed = patient.client.post(f"/api/investigations/{investigation['id']}/close", json={"version": 1})
    assert failed.status_code >= 500
    assert world.events("InvestigationClosed", investigation["id"]) == []
    db_session.expire_all()
    assert db_session.get(Investigation, investigation["id"]).status == "OPEN"


def test_cscw_ca_37_and_43_events_are_not_duplicated_by_repetition(db_session, world: World):
    """CSCW-CA-37/CSCW-CA-43: deferred prompt and effective read stay single-event."""
    patient, prompts = world.atypical_patient()
    doctor = world.doctor()
    world.active_link(patient, doctor)
    indicator_id = prompts[0]["indicator_id"]
    for _ in range(3):
        response = patient.client.post(f"/api/atypical-day-prompts/{indicator_id}/defer")
        assert response.status_code == 200 and response.json()["prompt"]["status"] == "deferred"
    deferred = [e for e in world.events("AtypicalDayInvestigationPromptDeferred")
                if (e.metadata_json or {}).get("daily_indicator_id") == indicator_id]
    assert len(deferred) == 1
    assert deferred[0].actor_user_id == world.account_id(patient) and deferred[0].source_type == "user"
    # A doctor cannot defer the patient's prompt.
    assert doctor.client.post(f"/api/atypical-day-prompts/{indicator_id}/defer").status_code in (403, 404)

    investigation = world.open_investigation(patient, doctor)
    for _ in range(3):
        assert doctor.client.post(f"/api/investigations/{investigation['id']}/read",
                                  json={"up_to_sequence": 1}).status_code == 200
    assert len(world.events("InvestigationReadAdvanced", investigation["id"])) == 1


def test_events_are_append_only_and_survive_close_and_revoke(db_session, world: World):
    """Supporting invariant: closing/revoking never cascades provenance away."""
    patient, doctor = world.patient(), world.doctor()
    link = world.active_link(patient, doctor)
    investigation = world.open_investigation(patient, doctor)
    assert doctor.client.post(f"/api/investigations/{investigation['id']}/messages", json={"content": "x"}).status_code == 201

    def fingerprint(entity_ids):
        return {
            event.id: (event.activity_type, event.entity_id, event.actor_user_id, event.source_type,
                       event.source_id, event.occurred_at, event.prov_json, event.metadata_json)
            for entity_id in entity_ids for event in world.events(entity_id=entity_id)
        }

    before = fingerprint([link["id"], investigation["id"]])
    assert len(before) >= 4
    assert patient.client.post(f"/api/investigations/{investigation['id']}/close", json={"version": 2}).status_code == 200
    assert patient.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": link["version"]}).status_code == 200
    after = fingerprint([link["id"], investigation["id"]])
    for event_id, row in before.items():
        assert after.get(event_id) == row, "historical event changed or disappeared"
    new_types = sorted(after[event_id][0] for event_id in after.keys() - before.keys())
    assert new_types == ["AssociationRevoked", "InvestigationClosed"]
