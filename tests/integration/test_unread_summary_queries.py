from types import SimpleNamespace

from sqlalchemy import event, func, select

from conftest import World
from app.db.session import SessionLocal, engine
from app.models.entities import Doctor, Notification, Patient, UserAccount
from app.services.investigations import notification_unread_summary


def test_summary_aggregates_all_counters_in_one_query_without_loading_bodies(world: World):
    patient, doctor = world.patient(), world.doctor()
    world.active_link(patient, doctor)
    conversations = [world.open_investigation(patient, doctor) for _ in range(3)]
    first = conversations[0]["id"]
    assert doctor.client.post(f"/api/investigations/{first}/read",
                              json={"up_to_sequence": 1}).status_code == 200
    assert doctor.client.post(f"/api/investigations/{first}/messages",
                              json={"content": "Reply"}).status_code == 201

    for actor, expected_messages in ((doctor, 2), (patient, 1)):
        account_id = world.account_id(actor)
        with SessionLocal() as db:
            principal = SimpleNamespace(
                account=db.get(UserAccount, account_id),
                doctor=db.get(Doctor, actor.id) if actor.role == "doctor" else None,
                patient=db.get(Patient, actor.id) if actor.role == "patient" else None,
            )
            expected_notifications = db.scalar(select(func.count(Notification.id)).where(
                Notification.recipient_user_account_id == account_id,
                Notification.read_at.is_(None),
            ))
            statements, loaded = [], []

            def sql(*args):
                statements.append(args[2])

            def entity(session, instance):
                loaded.append(instance)

            event.listen(engine, "before_cursor_execute", sql)
            event.listen(db, "loaded_as_persistent", entity)
            try:
                summary = notification_unread_summary(db, principal)
            finally:
                event.remove(engine, "before_cursor_execute", sql)
                event.remove(db, "loaded_as_persistent", entity)
            assert summary == {"notifications_unread": expected_notifications,
                               "messages_unread": expected_messages}
            assert len(statements) == 1
            assert loaded == []
