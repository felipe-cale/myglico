"""Durable outbox, retries and read-marker bookkeeping.

Covers CSCW-CA-29, CSCW-CA-44, CSCW-CA-19 and CSCW-CA-43 (the parts a browser
cannot observe), plus the "analysis_outbox is not a generic outbox" caution
from the coordinator decisions.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

from conftest import World


def _outbox_consumers() -> list[str]:
    """Names of app functions that look like a notification-outbox consumer/retrier."""
    import app.services as services

    found = []
    for module_info in pkgutil.iter_modules(services.__path__):
        module = importlib.import_module(f"app.services.{module_info.name}")
        for name in dir(module):
            lowered = name.lower()
            if callable(getattr(module, name)) and "outbox" in lowered and any(
                verb in lowered for verb in ("drain", "process", "dispatch", "publish", "deliver", "retry", "consume")
            ):
                found.append(f"{module_info.name}.{name}")
    return found


def test_cscw_ca_29_failed_publication_is_retried_from_a_durable_row_without_duplicate_effects(world: World):
    """CSCW-CA-29: event + outbox row commit with the mutation; retries are idempotent.

    Force the notification/graph publisher to fail, assert the operation still
    committed with a pending outbox row, run the retry path twice and assert
    exactly one visible effect per action.
    """
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import Notification, NotificationOutbox

    patient, doctor = world.patient(), world.doctor()
    link = world.request_link(patient, doctor)
    requested = world.events("AssociationRequested", link["id"])
    assert len(requested) == 1
    with SessionLocal() as db:
        notification = db.scalar(select(Notification).where(Notification.causation_event_id == requested[0].id))
        assert notification is not None
        outbox = list(db.scalars(select(NotificationOutbox).where(NotificationOutbox.notification_id == notification.id)))
        # Durable half: the outbox row committed atomically with the mutation and its event.
        assert len(outbox) == 1 and outbox[0].status == "PENDING" and outbox[0].attempts == 0

    consumers = _outbox_consumers()
    if not consumers:
        pytest.skip("B4 (REVISAO-FINAL.md): NotificationOutbox has no consumer/retry path; rows stay "
                    "PENDING forever, so publication failure and idempotent retry cannot be exercised. "
                    "Durable event+outbox commit was asserted above.")
    pytest.fail(f"An outbox consumer now exists ({consumers}); implement the retry assertions of CSCW-CA-29.")


def test_outbox_rows_never_expose_message_content_after_revocation(world: World):
    """CSCW-CA-29/CSCW-CA-08: queued items revalidate authorization on delivery."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import Notification, NotificationOutbox

    patient, doctor = world.patient(), world.doctor()
    link = world.active_link(patient, doctor)
    secret = "conteudo clinico sigiloso"
    investigation = world.open_investigation(patient, doctor, title="Titulo sigiloso", message=secret)
    sent = patient.client.post(f"/api/investigations/{investigation['id']}/messages", json={"content": secret + " 2"})
    assert sent.status_code == 201
    doctor_account = world.account_id(doctor)
    with SessionLocal() as db:
        queued = list(db.scalars(select(Notification).join(
            NotificationOutbox, NotificationOutbox.notification_id == Notification.id,
        ).where(Notification.recipient_user_account_id == doctor_account)))
        assert {n.notification_type for n in queued} >= {"investigation_opened", "investigation_message_added"}
        for item in queued:
            assert secret not in str(item.payload) and "Titulo sigiloso" not in str(item.payload)

    revoked = patient.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": link["version"]})
    assert revoked.status_code == 200
    inbox = doctor.client.get("/api/notifications")
    assert inbox.status_code == 200
    assert secret not in inbox.text and "Titulo sigiloso" not in inbox.text
    # Following any queued pointer after revocation yields no content.
    for item in inbox.json()["notifications"]:
        target = (item["payload"] or {}).get("investigation_id")
        if target:
            response = doctor.client.get(f"/api/investigations/{target}")
            assert response.status_code == 404 and secret not in response.text
    assert doctor.client.get("/api/notifications/unread-summary").json()["messages_unread"] == 0


def test_cscw_ca_44_persistence_recovers_counters_when_the_channel_is_down(world: World):
    """CSCW-CA-44: unread counters/notices are fully recoverable from the database."""
    from app.models.entities import Notification

    patient, doctor = world.patient(), world.doctor()
    world.active_link(patient, doctor)
    investigation = world.open_investigation(patient, doctor)
    # The doctor is "offline": its client is closed while the patient keeps writing.
    doctor.client.post("/api/auth/logout")
    for index in range(3):
        assert patient.client.post(f"/api/investigations/{investigation['id']}/messages",
                                   json={"content": f"offline {index}"}).status_code == 201

    reconnected = world.new_client()
    assert reconnected.post("/api/auth/login", json={"email": doctor.email, "password": doctor.password}).status_code == 200
    summary = reconnected.get("/api/notifications/unread-summary").json()
    assert summary["messages_unread"] == 4  # initial + 3 offline messages
    doctor_account = world.account_id(doctor)
    persisted_unread = world.count(Notification, Notification.recipient_user_account_id == doctor_account,
                                   Notification.read_at.is_(None))
    assert summary["notifications_unread"] == persisted_unread
    listing = reconnected.get("/api/notifications").json()
    assert listing["unread_count"] == persisted_unread
    detail = reconnected.get(f"/api/investigations/{investigation['id']}").json()
    assert detail["unread_count"] == 4 and detail["pagination"]["total"] == 4
    # A second, independent reconnect sees exactly the same state.
    again = world.new_client()
    assert again.post("/api/auth/login", json={"email": doctor.email, "password": doctor.password}).status_code == 200
    assert again.get("/api/notifications/unread-summary").json() == summary


def test_cscw_ca_19_read_advances_once_and_never_duplicates_events(world: World):
    """CSCW-CA-19: repeated reads with the same up_to_sequence add no new events."""
    from app.db.session import SessionLocal
    from app.models.entities import InvestigationReadPosition

    patient, doctor = world.patient(), world.doctor()
    world.active_link(patient, doctor)
    investigation = world.open_investigation(patient, doctor)
    doctor.client.post(f"/api/investigations/{investigation['id']}/messages", json={"content": "reply"})
    for _ in range(3):
        response = patient.client.post(f"/api/investigations/{investigation['id']}/read", json={"up_to_sequence": 2})
        assert response.status_code == 200 and response.json()["last_read_sequence"] == 2
    assert len(world.events("InvestigationReadAdvanced", investigation["id"])) == 1
    with SessionLocal() as db:
        position = db.get(InvestigationReadPosition, (investigation["id"], "PATIENT", patient.id))
        assert position.last_read_sequence == 2
    # Reading beyond what exists is rejected and changes nothing.
    assert patient.client.post(f"/api/investigations/{investigation['id']}/read", json={"up_to_sequence": 9}).status_code == 400
    assert len(world.events("InvestigationReadAdvanced", investigation["id"])) == 1


def test_cscw_ca_43_read_event_and_counter_move_exactly_once_per_effective_read(world: World):
    """CSCW-CA-43: an effective read produces one event, a correct counter and no repeats."""
    patient, doctor = world.patient(), world.doctor()
    world.active_link(patient, doctor)
    investigation = world.open_investigation(patient, doctor)
    url = f"/api/investigations/{investigation['id']}"
    for index in range(3):
        assert patient.client.post(f"{url}/messages", json={"content": f"m{index}"}).status_code == 201

    def unread():
        return doctor.client.get("/api/notifications/unread-summary").json()["messages_unread"]

    assert unread() == 4
    assert doctor.client.post(f"{url}/read", json={"up_to_sequence": 2}).json()["last_read_sequence"] == 2
    assert unread() == 2
    assert len(world.events("InvestigationReadAdvanced", investigation["id"])) == 1
    # lower sequence: no regression, no event
    assert doctor.client.post(f"{url}/read", json={"up_to_sequence": 1}).json()["last_read_sequence"] == 2
    assert unread() == 2
    assert len(world.events("InvestigationReadAdvanced", investigation["id"])) == 1
    # higher sequence: exactly one new event
    assert doctor.client.post(f"{url}/read", json={"up_to_sequence": 4}).json()["last_read_sequence"] == 4
    assert doctor.client.post(f"{url}/read", json={"up_to_sequence": 4}).json()["last_read_sequence"] == 4
    assert unread() == 0
    events = world.events("InvestigationReadAdvanced", investigation["id"])
    assert len(events) == 2
    assert [(e.metadata_json["last_read_sequence_before"], e.metadata_json["last_read_sequence_after"])
            for e in events] == [(0, 2), (2, 4)]
    # Reading a notification does not move the conversation read marker (and vice versa).
    patient_unread_before = patient.client.get("/api/notifications/unread-summary").json()
    note = patient.client.get("/api/notifications").json()["notifications"][0]
    patient.client.post(f"/api/notifications/{note['id']}/read")
    after = patient.client.get("/api/notifications/unread-summary").json()
    assert after["messages_unread"] == patient_unread_before["messages_unread"]
