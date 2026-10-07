"""Server-side authorization boundaries — API-level proofs for matrix criteria.

Covers AUT-CA-11, AUT-CA-12, AUT-CA-13, CSCW-CA-16, CSCW-CA-17 and
CSCW-CA-32. The browser suite repeats several of these through the UI; here
they are asserted directly against the HTTP surface with crafted payloads.
"""

from __future__ import annotations

from datetime import date

import pytest

from conftest import World

PERIOD = {"start_date": "2026-06-01", "end_date": "2026-06-30"}


def _patient_read_probes(patient_id: str) -> list[tuple[str, str, dict | None]]:
    return [
        ("GET", f"/api/patients/{patient_id}", None),
        ("GET", f"/api/patients/{patient_id}/report.pdf?start_date=2026-06-01&end_date=2026-06-30", None),
        ("GET", f"/api/patients/{patient_id}/atypical-days", None),
        ("GET", f"/api/patients/{patient_id}/atypical-day-prompts", None),
        ("POST", f"/api/patients/{patient_id}/glucose-records",
         {"measured_at": "2026-06-05T08:00:00", "glucose_mg_dl": 123, "context_label": "unspecified"}),
    ]


def _assert_denied_without_leak(response, *secrets: str) -> None:
    assert response.status_code in (401, 403, 404), (response.status_code, response.text[:200])
    assert not response.headers.get("content-type", "").startswith("application/pdf")
    for value in secrets:
        assert value not in response.text


def test_aut_ca_11_client_supplied_roles_and_ids_are_ignored(world: World):
    """AUT-CA-11: injected role/patient_id/doctor_id/user_account_id grant nothing."""
    from app.models.entities import GlucoseRecordSource, UserAccount

    victim, doctor = world.patient(), world.doctor()
    attacker_client = world.new_client()

    # Registration: privileged role and smuggled identifiers are rejected generically.
    for extra in ({"role": "admin"},
                  {"patient_id": victim.id}, {"doctor_id": doctor.id},
                  {"user_account_id": world.account_id(victim)}, {"is_demo": True}):
        payload = {**world.register_payload("patient"), **extra}
        response = attacker_client.post("/api/auth/register", json=payload)
        assert response.status_code == 422, (extra, response.status_code)
        assert response.json() == {"detail": "Invalid request."}
        assert payload["password"] not in response.text
    assert attacker_client.get("/api/auth/session").json() == {"authenticated": False}

    attacker = world.patient()
    # Login cannot carry a role either.
    attacker.client.post("/api/auth/logout")
    assert attacker.client.post("/api/auth/login", json={
        "email": attacker.email, "password": attacker.password, "role": "doctor",
    }).status_code == 422
    assert attacker.login().status_code == 200
    session = attacker.client.get("/api/auth/session").json()
    assert session["patient"]["id"] == attacker.id and "doctor" not in session

    # Link request: the patient side is always the session's patient.
    assert attacker.client.post("/api/doctor-links", json={
        "doctor_short_id": doctor.short_id, "patient_id": victim.id,
    }).status_code == 422
    # Investigation: a patient cannot name another patient as the subject.
    world.active_link(victim, doctor)
    response = attacker.client.post("/api/investigations", json={
        "patient_id": victim.id, "doctor_id": doctor.id, "title": "x", "initial_message": "y",
    })
    assert response.status_code in (400, 404)
    # A patient session cannot act as the doctor of the confirmation step.
    link = world.request_link(attacker, doctor)
    assert attacker.client.post(f"/api/doctor-links/{link['id']}/confirm", json={"version": 1}).status_code in (403, 404)

    # Manual entry: actor_user_id in the body is ignored; provenance uses the session account.
    from app.db.session import SessionLocal
    from sqlalchemy import select

    created = attacker.client.post(f"/api/patients/{attacker.id}/glucose-records", json={
        "measured_at": "2026-06-05T08:00:00", "glucose_mg_dl": 111, "context_label": "unspecified",
        "actor_user_id": world.account_id(victim),
    })
    assert created.status_code == 201, created.text
    with SessionLocal() as db:
        actors = set(db.scalars(select(GlucoseRecordSource.actor_user_id).where(
            GlucoseRecordSource.source_type == "manual",
            GlucoseRecordSource.actor_user_id.in_([world.account_id(victim), world.account_id(attacker)]),
        )))
        assert actors == {world.account_id(attacker)}
        assert db.get(UserAccount, world.account_id(victim)) is not None


def test_aut_ca_12_patient_a_cannot_read_patient_b_by_id_or_url(world: World):
    """AUT-CA-12: cross-patient reads are denied for JSON, downloads and PDF."""
    patient_a, patient_b = world.patient(), world.patient()
    world.seed_readings(patient_b.id)
    world.compute(patient_b.id)
    assert patient_b.client.get(f"/api/patients/{patient_b.id}").status_code == 200

    for method, url, body in _patient_read_probes(patient_b.id):
        response = patient_a.client.request(method, url, json=body)
        _assert_denied_without_leak(response, patient_b.display_name, patient_b.email)
    # The denial is indistinguishable from a non-existent id.
    unknown = patient_a.client.get("/api/patients/00000000-0000-0000-0000-000000000000")
    foreign = patient_a.client.get(f"/api/patients/{patient_b.id}")
    assert (unknown.status_code, unknown.json()) == (foreign.status_code, foreign.json())
    listing = patient_a.client.get("/api/patients").json()
    assert [row["id"] for row in listing["patients"]] == [patient_a.id]


def test_aut_ca_13_doctor_without_link_is_denied(world: World):
    """AUT-CA-13: a doctor with no ACTIVE link cannot read the patient."""
    patient, doctor_a, doctor_b, doctor_pending = world.patient(), world.doctor(), world.doctor(), world.doctor()
    world.seed_readings(patient.id)
    world.compute(patient.id)
    world.active_link(patient, doctor_a)
    world.request_link(patient, doctor_pending)  # PENDING is not ACTIVE
    investigation = world.open_investigation(patient, doctor_a, title="Private title")

    assert doctor_a.client.get(f"/api/patients/{patient.id}").status_code == 200
    for outsider in (doctor_b, doctor_pending):
        for method, url, body in _patient_read_probes(patient.id):
            response = outsider.client.request(method, url, json=body)
            _assert_denied_without_leak(response, patient.display_name, "Private title")
        assert outsider.client.get("/api/investigations").json()["investigations"] == []
        _assert_denied_without_leak(outsider.client.get(f"/api/investigations/{investigation['id']}"),
                                    "Private title", "Initial message")
        opened = outsider.client.post("/api/investigations", json={
            "patient_id": patient.id, "title": "probe", "initial_message": "probe",
        })
        assert opened.status_code == 404


def test_cscw_ca_16_event_from_another_patient_is_rejected_without_leakage(world: World):
    """CSCW-CA-16: opening with a foreign atypical-day event fails generically."""
    from app.models.entities import Investigation

    patient_a, patient_b, doctor = world.patient(), world.patient(), world.doctor()
    world.active_link(patient_a, doctor)
    own_event = world.seed_indicator(patient_a.id, date(2026, 5, 2))
    foreign_event = world.seed_indicator(patient_b.id, date(2026, 5, 3))
    unknown_event = "00000000-0000-0000-0000-000000000000"

    responses = []
    for event_id in (foreign_event, unknown_event):
        response = patient_a.client.post("/api/investigations", json={
            "doctor_id": doctor.id, "atypical_day_event_id": event_id,
            "title": "Cross patient", "initial_message": "Must be rejected",
        })
        _assert_denied_without_leak(response, patient_b.display_name, patient_b.id, "2026-05-03")
        responses.append((response.status_code, response.json()))
    # Foreign and non-existent events are indistinguishable.
    assert responses[0] == responses[1]
    assert world.count(Investigation, Investigation.atypical_day_event_id == foreign_event) == 0
    # The doctor (linked to A only) also cannot attach B's event.
    response = doctor.client.post("/api/investigations", json={
        "patient_id": patient_a.id, "atypical_day_event_id": foreign_event,
        "title": "Cross patient", "initial_message": "Must be rejected",
    })
    assert response.status_code == 404
    assert world.open_investigation(patient_a, doctor, event_id=own_event)["atypical_day_event_id"] == own_event


def test_cscw_ca_17_two_doctors_do_not_see_each_others_conversations(world: World):
    """CSCW-CA-17: list/detail endpoints never return another doctor's conversation."""
    from app.models.entities import InvestigationMessage

    patient, doctor_a, doctor_b = world.patient(), world.doctor(), world.doctor()
    world.active_link(patient, doctor_a)
    world.active_link(patient, doctor_b)
    inv_a = world.open_investigation(patient, doctor_a, title="Only for A", message="Secret to A")
    inv_b = world.open_investigation(patient, doctor_b, title="Only for B", message="Secret to B")

    assert {row["id"] for row in doctor_a.client.get("/api/investigations").json()["investigations"]} == {inv_a["id"]}
    assert {row["id"] for row in doctor_b.client.get("/api/investigations").json()["investigations"]} == {inv_b["id"]}
    assert doctor_b.client.get(f"/api/investigations?counterpart_id={patient.id}").json()["investigations"][0]["id"] == inv_b["id"]

    probes = [
        ("GET", f"/api/investigations/{inv_a['id']}", None),
        ("POST", f"/api/investigations/{inv_a['id']}/messages", {"content": "intrusion"}),
        ("POST", f"/api/investigations/{inv_a['id']}/read", {"up_to_sequence": 1}),
        ("POST", f"/api/investigations/{inv_a['id']}/close", {"version": 1}),
    ]
    for method, url, body in probes:
        response = doctor_b.client.request(method, url, json=body)
        assert response.status_code == 404, (url, response.status_code)
        for leaked in ("Only for A", "Secret to A", doctor_a.display_name):
            assert leaked not in response.text
    assert world.count(InvestigationMessage, InvestigationMessage.investigation_id == inv_a["id"]) == 1
    assert doctor_a.client.get(f"/api/investigations/{inv_a['id']}").json()["investigation"]["status"] == "open"
    summary = doctor_b.client.get("/api/notifications/unread-summary").json()
    assert summary["messages_unread"] == 1  # only B's own conversation


def test_cscw_ca_32_revoked_doctor_cannot_use_provenance_or_audit_endpoints(world: World):
    """CSCW-CA-32: revocation also blocks provenance/history queries."""
    patient, doctor = world.patient(), world.doctor()
    world.seed_readings(patient.id)
    world.compute(patient.id)
    link = world.active_link(patient, doctor)
    investigation = world.open_investigation(patient, doctor, title="History title", message="History body")

    provenance_paths = sorted(
        route.path for route in world.app.routes
        if "GET" in getattr(route, "methods", set())
        and ("provenance" in getattr(route, "path", "") or "history" in getattr(route, "path", ""))
    )

    def concrete(path: str) -> str:
        return path.replace("{patient_id}", patient.id).replace("{investigation_id}", investigation["id"])

    # While the link is ACTIVE the doctor is authorized, so a later denial is due to revocation.
    assert doctor.client.get(f"/api/patients/{patient.id}").status_code == 200
    for path in provenance_paths:
        assert doctor.client.get(concrete(path)).status_code == 200, path

    revoked = patient.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": link["version"]})
    assert revoked.status_code == 200

    # Every history-bearing endpoint denies the revoked doctor without leaking content.
    probes = _patient_read_probes(patient.id) + [("GET", f"/api/investigations/{investigation['id']}", None)]
    probes += [("GET", concrete(path), None) for path in provenance_paths]
    for method, url, body in probes:
        _assert_denied_without_leak(doctor.client.request(method, url, json=body),
                                    "History title", "History body", patient.display_name)
    assert doctor.client.get("/api/investigations").json()["investigations"] == []
    # The patient keeps the history.
    assert patient.client.get(f"/api/investigations/{investigation['id']}").status_code == 200
    for path in provenance_paths:
        assert patient.client.get(concrete(path)).status_code == 200, path

    if not provenance_paths:
        pytest.skip("A12 (REVISAO-FINAL.md): no authorized provenance/history endpoint exists "
                    "(SDD2 §10.6), so the provenance half of CSCW-CA-32 cannot be exercised; "
                    "clinical/investigation history denial for the revoked doctor was asserted above.")


def test_persistence_layer_scopes_every_query_by_session_identity(world: World):
    """Supporting invariant: resource queries are always filtered by the session's actor."""
    owner, stranger_patient, stranger_doctor = world.patient(), world.patient(), world.doctor()
    world.seed_readings(owner.id)
    world.compute(owner.id)

    templated = []
    for route in world.app.routes:
        path = getattr(route, "path", "")
        if "{patient_id}" in path and "GET" in getattr(route, "methods", set()):
            templated.append(path)
    assert len(templated) >= 4, templated
    for path in templated:
        url = path.replace("{patient_id}", owner.id)
        params = PERIOD if path.endswith("report.pdf") else None
        assert owner.client.get(url, params=params).status_code == 200, url
        for stranger in (stranger_patient, stranger_doctor):
            response = stranger.client.get(url, params=params)
            _assert_denied_without_leak(response, owner.display_name)
