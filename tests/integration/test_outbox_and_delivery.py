"""Durable outbox, retries and read-marker bookkeeping.

Covers CSCW-CA-29, CSCW-CA-44, CSCW-CA-19 and CSCW-CA-43 (the parts a browser
cannot observe), plus the "analysis_outbox is not a generic outbox" caution
from the coordinator decisions.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from conftest import World


def _drain_until_idle(outbox_service, db) -> dict[str, int]:
    """Drain every due row: earlier tests may leave more than one batch pending."""
    totals = {"delivered": 0, "failed": 0, "processed": 0}
    for _ in range(50):
        result = outbox_service.drain_notification_outbox(db)
        for key in totals:
            totals[key] += result[key]
        if result["processed"] == 0:
            return totals
    raise AssertionError("outbox did not reach an idle state")


def test_cscw_ca_29_failed_publication_is_retried_from_a_durable_row_without_duplicate_effects(
    world: World, monkeypatch,
):
    """CSCW-CA-29: event + outbox row commit with the mutation; retries are idempotent.

    Force the notification/graph publisher to fail, assert the operation still
    committed with a pending outbox row, run the retry path twice and assert
    exactly one visible effect per action.
    """
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models.entities import Notification, NotificationOutbox
    import app.services.notification_outbox as outbox_service

    patient, doctor = world.patient(), world.doctor()
    link = world.request_link(patient, doctor)
    requested = world.events("AssociationRequested", link["id"])
    assert len(requested) == 1
    with SessionLocal() as db:
        notification = db.scalar(select(Notification).where(Notification.causation_event_id == requested[0].id))
        assert notification is not None
        outbox = list(db.scalars(select(NotificationOutbox).where(NotificationOutbox.notification_id == notification.id)))
        # Committed with the mutation; the request itself never drains (O8).
        assert len(outbox) == 1 and outbox[0].status == "PENDING" and outbox[0].attempts == 0
        first_id = outbox[0].id
    # The inbox item is visible before any dispatcher run.
    inbox = doctor.client.get("/api/notifications")
    assert inbox.status_code == 200, inbox.text
    with SessionLocal() as db:
        _drain_until_idle(outbox_service, db)
        row = db.get(NotificationOutbox, first_id)
        assert row.status == "DELIVERED" and row.attempts == 1 and row.processed_at is not None

    def fail_delivery(db, notification):
        raise RuntimeError("private notification content must not be persisted")

    monkeypatch.setattr(outbox_service, "_deliver_to_in_app_inbox", fail_delivery)
    retry_doctor = world.doctor()
    retry_link = world.request_link(patient, retry_doctor)
    retry_event = world.events("AssociationRequested", retry_link["id"])[0]
    with SessionLocal() as db:
        result = _drain_until_idle(outbox_service, db)
        assert result["failed"] >= 1
        notification = db.scalar(select(Notification).where(Notification.causation_event_id == retry_event.id))
        row = db.scalar(select(NotificationOutbox).where(NotificationOutbox.notification_id == notification.id))
        assert row.status == "PENDING" and row.attempts == 1
        assert row.next_attempt_at is not None and row.last_error == "RuntimeError"
        assert "private notification content" not in (row.last_error or "")
        retry_id = row.id
        row.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()

    monkeypatch.setattr(outbox_service, "_deliver_to_in_app_inbox", lambda db, notification: None)
    with SessionLocal() as db:
        result = _drain_until_idle(outbox_service, db)
        row = db.get(NotificationOutbox, retry_id)
        assert result["delivered"] >= 1 and result["failed"] == 0
        assert row.status == "DELIVERED" and row.attempts == 2 and row.processed_at is not None
        assert row.next_attempt_at is None and row.last_error is None
        visible_count = db.scalar(select(func.count(Notification.id)).where(
            Notification.causation_event_id == retry_event.id
        ))
        assert visible_count == 1, "a retry must not duplicate the durable inbox item"


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


def test_o8_api_requests_never_drain_the_outbox(world: World):
    """O8: the response path no longer runs the outbox consumer."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import Notification, NotificationOutbox

    patient, doctor = world.patient(), world.doctor()
    link = world.request_link(patient, doctor)
    for _ in range(3):
        assert doctor.client.get("/api/notifications").status_code == 200
        assert patient.client.get("/api/doctor-links").status_code == 200
    event = world.events("AssociationRequested", link["id"])[0]
    with SessionLocal() as db:
        notification = db.scalar(select(Notification).where(Notification.causation_event_id == event.id))
        row = db.scalar(select(NotificationOutbox).where(NotificationOutbox.notification_id == notification.id))
        assert (row.status, row.attempts) == ("PENDING", 0)


def test_o8_dispatcher_loop_is_off_in_tests_and_drains_when_enabled(monkeypatch):
    import asyncio

    import app.main as main_module

    assert main_module.settings.notification_dispatcher == "off"
    calls = []
    monkeypatch.setattr(main_module, "_drain_outbox_once", lambda: calls.append(1))

    async def scenario():
        task = asyncio.create_task(main_module._notification_dispatch_loop(0.01))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())
    assert len(calls) >= 2
