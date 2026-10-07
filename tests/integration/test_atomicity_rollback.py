"""Atomicity and rollback — criteria the UI cannot prove.

Covers AUT-CA-05, CSCW-CA-28 and the atomic initial message of CSCW-CA-13.
Failures are injected with SQLite ``BEFORE INSERT`` triggers on the isolated
integration database, so the real service code runs unmodified.
"""

from __future__ import annotations

from conftest import World


def test_aut_ca_05_failed_domain_creation_leaves_no_orphan_account(world: World):
    """AUT-CA-05: registration rolls back — no orphan UserAccount remains.

    Force the domain step (Patient/Doctor insert) to fail after the account
    row is written (e.g. injected constraint violation), assert the request
    fails with a generic error and that a SELECT for the e-mail index returns
    nothing.
    """
    from app.core.crypto import email_lookup
    from app.models.entities import Doctor, Patient, UserAccount, UserSession

    for role, table, model in (("patient", "patients", Patient), ("doctor", "doctors", Doctor)):
        client = world.new_client()
        payload = world.register_payload(role)
        accounts_before = world.count(UserAccount)
        domain_before = world.count(model)
        sessions_before = world.count(UserSession)
        with world.failing_insert(table):
            response = client.post("/api/auth/register", json=payload)

        assert response.status_code >= 400, response.text
        assert payload["password"] not in response.text and payload["email"] not in response.text
        assert "forced integration failure" not in response.text
        assert "myglico_session" not in response.headers.get("set-cookie", "")
        assert world.count(UserAccount, UserAccount.email_lookup == email_lookup(payload["email"])) == 0
        assert world.count(UserAccount) == accounts_before
        assert world.count(model) == domain_before
        assert world.count(UserSession) == sessions_before

        # Nothing was left half-created: the same e-mail registers cleanly afterwards.
        retry = client.post("/api/auth/register", json=payload)
        assert retry.status_code == 201, retry.text


def test_cscw_ca_28_provenance_write_failure_reverts_the_domain_mutation(world: World):
    """CSCW-CA-28: if provenance cannot be persisted, the mutation is reverted.

    Monkeypatch the provenance writer to raise, trigger a link transition
    (request/confirm/revoke), and assert the state did not change and no
    success event exists ("no success without an event").
    """
    from app.db.session import SessionLocal
    from app.models.entities import Notification, PatientDoctorLink

    patient, doctor = world.patient(), world.doctor()
    patient_account, doctor_account = world.account_id(patient), world.account_id(doctor)

    # request: no link, no notification when AssociationRequested cannot be written
    with world.failing_insert("provenance_events", "NEW.activity_type = 'AssociationRequested'"):
        failed = patient.client.post("/api/doctor-links", json={"doctor_short_id": doctor.short_id})
    assert failed.status_code >= 500
    assert world.count(PatientDoctorLink, PatientDoctorLink.patient_id == patient.id) == 0
    assert world.count(Notification, Notification.recipient_user_account_id == doctor_account) == 0

    # confirm: link stays PENDING/v1, no AssociationConfirmed, patient not notified
    link = world.request_link(patient, doctor)
    with world.failing_insert("provenance_events", "NEW.activity_type = 'AssociationConfirmed'"):
        failed = doctor.client.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": 1})
    assert failed.status_code >= 500
    with SessionLocal() as db:
        stored = db.get(PatientDoctorLink, link["id"])
        assert (stored.status, stored.version) == ("PENDING", 1)
    assert world.events("AssociationConfirmed", link["id"]) == []
    assert world.count(Notification, Notification.recipient_user_account_id == patient_account) == 0
    assert doctor.client.get(f"/api/patients/{patient.id}").status_code == 404

    # revoke: link stays ACTIVE, open investigation stays OPEN, no revocation events
    confirmed = doctor.client.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": 1})
    assert confirmed.status_code == 200
    investigation = world.open_investigation(patient, doctor)
    with world.failing_insert("provenance_events", "NEW.activity_type = 'AssociationRevoked'"):
        failed = patient.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": 2})
    assert failed.status_code >= 500
    with SessionLocal() as db:
        stored = db.get(PatientDoctorLink, link["id"])
        assert (stored.status, stored.version, stored.revoked_at) == ("ACTIVE", 2, None)
    assert world.events("AssociationRevoked", link["id"]) == []
    assert world.events("InvestigationClosedByAssociationRevocation", investigation["id"]) == []
    detail = doctor.client.get(f"/api/investigations/{investigation['id']}")
    assert detail.status_code == 200 and detail.json()["investigation"]["status"] == "open"


def test_cscw_ca_13_investigation_message_and_provenance_commit_together(world: World):
    """CSCW-CA-13: investigation + initial message + event + notification are atomic.

    Inject a failure on one of the later writes and assert nothing from the
    operation survives (no investigation without its initial message, no
    notification without the investigation).
    """
    from app.models.entities import (
        Investigation, InvestigationMessage, Notification, NotificationOutbox, ProvenanceEvent,
    )

    patient, doctor = world.patient(), world.doctor()
    world.active_link(patient, doctor)
    doctor_account = world.account_id(doctor)
    baseline = {
        "investigations": world.count(Investigation, Investigation.patient_id == patient.id),
        "messages": world.count(InvestigationMessage),
        "opened": world.count(ProvenanceEvent, ProvenanceEvent.activity_type == "InvestigationOpened"),
        "msg_events": world.count(ProvenanceEvent, ProvenanceEvent.activity_type == "InvestigationMessageAdded"),
        "notifications": world.count(Notification, Notification.recipient_user_account_id == doctor_account),
        "outbox": world.count(NotificationOutbox),
    }

    def snapshot():
        return {
            "investigations": world.count(Investigation, Investigation.patient_id == patient.id),
            "messages": world.count(InvestigationMessage),
            "opened": world.count(ProvenanceEvent, ProvenanceEvent.activity_type == "InvestigationOpened"),
            "msg_events": world.count(ProvenanceEvent, ProvenanceEvent.activity_type == "InvestigationMessageAdded"),
            "notifications": world.count(Notification, Notification.recipient_user_account_id == doctor_account),
            "outbox": world.count(NotificationOutbox),
        }

    body = {"doctor_id": doctor.id, "title": "Atomic", "initial_message": "Must not survive"}
    # Fail the very last write of the unit (outbox row), then the notification itself.
    for table, when in (("notification_outbox", "1"),
                        ("notifications", "NEW.notification_type = 'investigation_opened'")):
        with world.failing_insert(table, when):
            response = patient.client.post("/api/investigations", json=body)
        assert response.status_code >= 500, response.text
        assert snapshot() == baseline, table

    assert patient.client.get("/api/investigations").json()["investigations"] == []
    ok = patient.client.post("/api/investigations", json=body)
    assert ok.status_code == 201
    after = snapshot()
    assert after["investigations"] == baseline["investigations"] + 1
    assert after["messages"] == baseline["messages"] + 1
    assert after["notifications"] == baseline["notifications"] + 1


def test_domain_mutation_and_provenance_event_share_one_transaction(world: World):
    """Supporting invariant: event and mutation commit or roll back together."""
    from app.db.session import SessionLocal
    from app.models.entities import Investigation, InvestigationMessage

    patient, doctor = world.patient(), world.doctor()
    world.active_link(patient, doctor)
    investigation = world.open_investigation(patient, doctor)

    # The message insert, version bump and InvestigationMessageAdded happen before
    # the NotificationCreated event; failing that last insert must undo all of them.
    with world.failing_insert("provenance_events", "NEW.activity_type = 'NotificationCreated'"):
        failed = doctor.client.post(f"/api/investigations/{investigation['id']}/messages",
                                    json={"content": "Rolled back reply"})
    # append_message maps the aborted INSERT (IntegrityError) to a generic 409.
    assert failed.status_code in (409, 500), failed.text
    assert world.count(InvestigationMessage, InvestigationMessage.investigation_id == investigation["id"]) == 1
    assert len(world.events("InvestigationMessageAdded", investigation["id"])) == 1
    with SessionLocal() as db:
        stored = db.get(Investigation, investigation["id"])
        assert (stored.version, stored.awaiting_role) == (1, "DOCTOR")

    ok = doctor.client.post(f"/api/investigations/{investigation['id']}/messages", json={"content": "Reply"})
    assert ok.status_code == 201 and ok.json()["message"]["sequence"] == 2
    assert len(world.events("InvestigationMessageAdded", investigation["id"])) == 2
