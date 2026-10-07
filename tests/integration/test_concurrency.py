"""Collisions, races and optimistic locking — criteria the UI cannot prove.

Covers AUT-CA-09, AUT-CA-18, CSCW-CA-30 and the confirm/confirm race behind
CSCW-CA-03/CSCW-CA-04. Races are real: requests are fired from a thread pool,
one TestClient per thread, released together by a barrier, against the
isolated SQLite file.
"""

from __future__ import annotations

import secrets as std_secrets
import threading
import types
from concurrent.futures import ThreadPoolExecutor

from conftest import World


def _race(calls):
    """Run zero-arg callables simultaneously; return their results in order."""
    barrier = threading.Barrier(len(calls))

    def run(call):
        barrier.wait()
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


def test_aut_ca_09_concurrent_registration_keeps_e_mail_uniqueness(world: World):
    """AUT-CA-09: concurrent registration of the same e-mail keeps one account.

    Fire N parallel registrations for one normalised e-mail; assert exactly one
    2xx, the others fail generically, and the protected index holds one row.
    """
    from app.core.crypto import email_lookup
    from app.models.entities import Patient, UserAccount

    email = world.unique_email("race")
    variants = [email, email.upper(), f"  {email}  ", email.title(), email, email]
    payloads = [world.register_payload("patient", email=variant) for variant in variants]
    clients = [world.new_client() for _ in payloads]
    responses = _race([
        (lambda c=c, p=p: c.post("/api/auth/register", json=p)) for c, p in zip(clients, payloads)
    ])

    statuses = sorted(r.status_code for r in responses)
    assert statuses.count(201) == 1, statuses
    for response in responses:
        if response.status_code != 201:
            assert response.status_code == 409, (response.status_code, response.text)
            assert response.json() == {"detail": "Account could not be created."}
    lookup = email_lookup(email)
    assert world.count(UserAccount, UserAccount.email_lookup == lookup) == 1
    from app.db.session import SessionLocal
    from sqlalchemy import select

    with SessionLocal() as db:
        account_id = db.scalar(select(UserAccount.id).where(UserAccount.email_lookup == lookup))
        assert world.count(Patient, Patient.user_account_id == account_id) == 1
    # Exactly the winner's password works.
    winner = payloads[[r.status_code for r in responses].index(201)]
    login = world.new_client().post("/api/auth/login", json={"email": email, "password": winner["password"]})
    assert login.status_code == 200


def test_aut_ca_18_short_id_collision_regenerates_without_overwrite(world: World, monkeypatch):
    """AUT-CA-18: a simulated SHORTID collision triggers a retry, never a duplicate.

    Pre-seed a Patient/Doctor with a chosen short id, patch the generator to
    emit that value once, create a new record and assert a different id was
    assigned and the existing row is untouched.
    """
    import app.core.crypto as crypto
    from app.db.session import SessionLocal
    from app.models.entities import Doctor, Patient

    for factory, model in ((world.patient, Patient), (world.doctor, Doctor)):
        seeded = factory()
        with SessionLocal() as db:
            before = db.get(model, seeded.id)
            before_state = (before.short_id, before.user_account_id, bytes(before.name_encrypted))

        forced = list(seeded.short_id)
        calls = {"count": 0}

        def colliding_choice(seq, _forced=forced, _calls=calls):
            _calls["count"] += 1
            if _forced:
                return _forced.pop(0)
            return std_secrets.choice(seq)

        fake_secrets = types.SimpleNamespace(choice=colliding_choice, token_bytes=std_secrets.token_bytes)
        monkeypatch.setattr(crypto, "secrets", fake_secrets)
        try:
            newcomer = factory()
        finally:
            monkeypatch.setattr(crypto, "secrets", std_secrets)

        assert forced == [], "the colliding candidate was never drawn"
        assert calls["count"] >= 12, "generator did not retry after the collision"
        assert newcomer.short_id != seeded.short_id and len(newcomer.short_id) == 6
        assert world.count(model, model.short_id == seeded.short_id) == 1
        with SessionLocal() as db:
            after = db.get(model, seeded.id)
            assert (after.short_id, after.user_account_id, bytes(after.name_encrypted)) == before_state


def test_cscw_ca_30_concurrent_confirm_and_revoke_resolve_to_valid_transitions(world: World):
    """CSCW-CA-30: concurrent confirm/revoke/send produce only valid transitions.

    Race confirm against revoke, and message send against close/revoke. Assert
    the final state is one of the legal states, stale versions get 409, and no
    message lands after CLOSED/REVOKED.
    """
    from app.db.session import SessionLocal
    from app.models.entities import Investigation, InvestigationMessage, PatientDoctorLink
    from sqlalchemy import select

    # 1) confirm (doctor) vs cancel (patient) on the same PENDING v1
    patient, doctor = world.patient(), world.doctor()
    link = world.request_link(patient, doctor)
    confirm, cancel = _race([
        lambda: doctor.client.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": 1}),
        lambda: patient.client.post(f"/api/doctor-links/{link['id']}/cancel", json={"version": 1}),
    ])
    codes = sorted([confirm.status_code, cancel.status_code])
    assert codes == [200, 409], (confirm.text, cancel.text)
    with SessionLocal() as db:
        stored = db.get(PatientDoctorLink, link["id"])
        assert stored.status in ("ACTIVE", "CANCELLED") and stored.version == 2
    confirmed = len(world.events("AssociationConfirmed", link["id"]))
    cancelled = len(world.events("AssociationRequestCancelled", link["id"]))
    assert (confirmed, cancelled) == ((1, 0) if stored.status == "ACTIVE" else (0, 1))

    # 2) stale versions are refused
    patient2, doctor2 = world.patient(), world.doctor()
    active = world.active_link(patient2, doctor2)
    assert patient2.client.post(f"/api/doctor-links/{active['id']}/revoke", json={"version": 1}).status_code == 409

    # 3) message sends racing a revoke: nothing lands after the investigation is closed
    investigation = world.open_investigation(patient2, doctor2)
    calls = [lambda i=i: doctor2.client.post(f"/api/investigations/{investigation['id']}/messages",
                                             json={"content": f"race {i}"}) for i in range(4)]
    calls.append(lambda: patient2.client.post(f"/api/doctor-links/{active['id']}/revoke",
                                              json={"version": active["version"]}))
    results = _race(calls)
    assert results[-1].status_code == 200, results[-1].text
    sent = [r for r in results[:-1] if r.status_code == 201]
    assert all(r.status_code in (201, 404, 409) for r in results[:-1]), [r.status_code for r in results]
    with SessionLocal() as db:
        stored = db.get(Investigation, investigation["id"])
        assert (stored.status, stored.closed_reason) == ("CLOSED", "ASSOCIATION_REVOKED")
        messages = list(db.scalars(
            select(InvestigationMessage)
            .where(InvestigationMessage.investigation_id == investigation["id"])
        ))
        assert len(messages) == 1 + len(sent)
        assert sorted(m.sequence for m in messages) == list(range(1, len(messages) + 1))
        assert all(m.created_at <= stored.closed_at for m in messages)
    assert len(world.events("InvestigationMessageAdded", investigation["id"])) == len(messages)

    # 4) message sends racing a participant close
    patient3, doctor3 = world.patient(), world.doctor()
    world.active_link(patient3, doctor3)
    inv = world.open_investigation(patient3, doctor3)
    calls = [lambda i=i: patient3.client.post(f"/api/investigations/{inv['id']}/messages",
                                              json={"content": f"late {i}"}) for i in range(3)]
    calls.append(lambda: doctor3.client.post(f"/api/investigations/{inv['id']}/close", json={"version": 1}))
    results = _race(calls)
    close = results[-1]
    assert close.status_code in (200, 409), close.text
    if close.status_code == 409:  # a message bumped the version first; close again with the fresh version
        version = doctor3.client.get(f"/api/investigations/{inv['id']}").json()["investigation"]["version"]
        assert doctor3.client.post(f"/api/investigations/{inv['id']}/close", json={"version": version}).status_code == 200
    assert patient3.client.post(f"/api/investigations/{inv['id']}/messages", json={"content": "after"}).status_code == 409
    with SessionLocal() as db:
        stored = db.get(Investigation, inv["id"])
        assert stored.status == "CLOSED"
        late = world.count(InvestigationMessage, InvestigationMessage.investigation_id == inv["id"],
                           InvestigationMessage.created_at > stored.closed_at)
        assert late == 0


def test_double_confirm_of_one_request_yields_single_transition_and_event(world: World):
    """CSCW-CA-30/CSCW-CA-04: two confirms -> one ACTIVE transition, one success event."""
    from app.db.session import SessionLocal
    from app.models.entities import Notification, PatientDoctorLink

    patient, doctor = world.patient(), world.doctor()
    link = world.request_link(patient, doctor)
    results = _race([
        (lambda: doctor.client.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": 1}))
        for _ in range(3)
    ])
    assert all(r.status_code in (200, 409) for r in results), [r.text for r in results]
    assert any(r.status_code == 200 for r in results)
    with SessionLocal() as db:
        stored = db.get(PatientDoctorLink, link["id"])
        assert (stored.status, stored.version) == ("ACTIVE", 2)
    assert len(world.events("AssociationConfirmed", link["id"])) == 1
    patient_account = world.account_id(patient)
    assert world.count(Notification, Notification.recipient_user_account_id == patient_account,
                       Notification.notification_type == "association_confirmed") == 1


def test_repeated_revoke_does_not_create_new_success_events(world: World):
    """CSCW-CA-30: revoking an already revoked link adds no success event."""
    patient, doctor = world.patient(), world.doctor()
    link = world.active_link(patient, doctor)
    first = patient.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": link["version"]})
    assert first.status_code == 200
    for actor, version in ((patient, link["version"]), (patient, link["version"] + 1), (doctor, link["version"] + 1)):
        again = actor.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": version})
        assert again.status_code == 409, again.text
    # and concurrently
    results = _race([
        (lambda: doctor.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": link["version"]}))
        for _ in range(3)
    ])
    assert all(r.status_code == 409 for r in results)
    assert len(world.events("AssociationRevoked", link["id"])) == 1
