from __future__ import annotations

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import uuid

import pytest
from sqlalchemy import func, select

from conftest import IS_SQLITE, World


def _csrf(actor):
    response = actor.client.get("/api/glico/csrf")
    assert response.status_code == 200, response.text
    return {"x-myglico-csrf": response.json()["token"], "origin": "https://testserver"}


def _conversation(actor, headers, patient_id=None):
    response = actor.client.post("/api/glico/conversations", headers=headers,
        json={"locale": "pt-BR", "client_request_id": str(uuid.uuid4())})
    assert response.status_code == 201, response.text
    conversation_id = response.json()["id"]
    if patient_id:
        changed = actor.client.patch(f"/api/glico/conversations/{conversation_id}/context",
            headers=headers, json={"version": 1, "patient_id": patient_id})
        assert changed.status_code == 200, changed.text
        return conversation_id, changed.json()["context_version"]
    return conversation_id, response.json()["context_version"]


def _draft(actor, headers, conversation_id, context_version):
    response = actor.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": "128 mg/dL", "context_version": context_version,
              "client_request_id": str(uuid.uuid4())})
    assert response.status_code == 200, response.text
    assert response.json()["type"] == "proposal"
    proposal = response.json()["proposal"]
    # No date/time stated: the reading defaults to now and is ready for review.
    assert proposal["state"] == "READY"
    assert proposal["fields"]["measured_at"]
    edit = actor.client.patch(f"/api/glico/proposals/{proposal['id']}", headers=headers,
        json={"version": proposal["version"], "context_version": context_version,
              "fields": {"measured_at": "2026-10-13T08:00:00-03:00", "timezone": "America/Sao_Paulo"}})
    assert edit.status_code == 200, edit.text
    assert edit.json()["proposal"]["state"] == "READY"
    return edit.json()["proposal"]


def test_glico_csrf_is_required_and_payload_rejects_identity_fields(world: World):
    patient = world.patient()
    response = patient.client.post("/api/glico/conversations", json={
        "locale": "pt-BR", "client_request_id": str(uuid.uuid4()), "owner_account_id": "forged"})
    assert response.status_code == 422
    response = patient.client.post("/api/glico/conversations", json={
        "locale": "pt-BR", "client_request_id": str(uuid.uuid4())})
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_failed"
    headers = _csrf(patient)
    hostile = patient.client.post("/api/glico/conversations", headers={**headers, "origin": "https://evil.example"}, json={
        "locale": "pt-BR", "client_request_id": str(uuid.uuid4())})
    assert hostile.status_code == 403
    assert hostile.json()["detail"] == "csrf_failed"
    headers = _csrf(patient)
    response = patient.client.post("/api/glico/conversations", headers=headers, json={
        "locale": "pt-BR", "client_request_id": str(uuid.uuid4())})
    assert response.status_code == 201, response.text


def test_glico_sensitive_responses_are_no_store_and_origin_null_is_rejected(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, context_version = _conversation(patient, headers)
    read = patient.client.get(f"/api/glico/conversations/{conversation_id}")
    assert read.status_code == 200
    assert read.headers.get("cache-control") == "no-store, private"
    create = patient.client.post("/api/glico/conversations", headers={**headers, "origin": "null"}, json={
        "locale": "pt-BR", "client_request_id": str(uuid.uuid4())})
    assert create.status_code == 403
    invalid_token = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages",
        headers={**headers, "x-myglico-csrf": "invalid"}, json={
            "text": "128 mg/dL", "context_version": context_version,
            "client_request_id": str(uuid.uuid4())})
    assert invalid_token.status_code == 403


def test_glico_foreign_and_missing_ids_are_indistinguishable(world: World):
    owner = world.patient()
    attacker = world.patient()
    owner_headers = _csrf(owner)
    conversation_id, context_version = _conversation(owner, owner_headers)
    proposal = owner.client.post(f"/api/glico/conversations/{conversation_id}/messages",
        headers=owner_headers, json={"text": "128 mg/dL", "context_version": context_version,
                                     "client_request_id": str(uuid.uuid4())}).json()["proposal"]
    attacker_headers = _csrf(attacker)
    foreign_conversation = attacker.client.get(f"/api/glico/conversations/{conversation_id}")
    missing_conversation = attacker.client.get(f"/api/glico/conversations/{uuid.uuid4()}")
    assert foreign_conversation.status_code == missing_conversation.status_code == 404
    assert foreign_conversation.json() == missing_conversation.json()
    foreign_proposal = attacker.client.get(f"/api/glico/proposals/{proposal['id']}")
    missing_proposal = attacker.client.get(f"/api/glico/proposals/{uuid.uuid4()}")
    assert foreign_proposal.status_code == missing_proposal.status_code == 404
    assert foreign_proposal.json() == missing_proposal.json()
    post = attacker.client.post(f"/api/glico/conversations/{conversation_id}/messages",
        headers=attacker_headers, json={"text": "128 mg/dL", "context_version": 1,
                                       "client_request_id": str(uuid.uuid4())})
    assert post.status_code == 404
    proposal_payload = {"version": 1, "context_version": 1,
        "fields": {"measured_at": "2026-10-13T08:00:00-03:00", "timezone": "America/Sao_Paulo"}}
    confirm_payload = {"version": 1, "context_version": 1, "idempotency_key": str(uuid.uuid4())}
    media_headers = {**attacker_headers, "content-type": "application/octet-stream",
        "x-glico-context-version": "1", "x-glico-request-id": str(uuid.uuid4())}
    probes = [
        attacker.client.patch(f"/api/glico/conversations/{conversation_id}/context",
            headers=attacker_headers, json={"version": 1}),
        attacker.client.post(f"/api/glico/conversations/{conversation_id}/collaboration-proposals",
            headers=attacker_headers, json={"kind": "investigation_open", "title": "x", "content": "y"}),
        *(attacker.client.post(f"/api/glico/conversations/{conversation_id}/extract/{kind}",
            headers={**media_headers, "x-glico-request-id": str(uuid.uuid4())}, content=b"synthetic")
          for kind in ("image", "audio")),
        attacker.client.patch(f"/api/glico/proposals/{proposal['id']}",
            headers=attacker_headers, json=proposal_payload),
        attacker.client.post(f"/api/glico/proposals/{proposal['id']}/confirm",
            headers=attacker_headers, json=confirm_payload),
        attacker.client.post(f"/api/glico/proposals/{proposal['id']}/cancel",
            headers=attacker_headers, json={"version": 1}),
    ]
    assert [response.status_code for response in probes] == [404] * len(probes)


def test_glico_proposal_confirmation_is_versioned_idempotent_and_atomic(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, context_version = _conversation(patient, headers)
    proposal = _draft(patient, headers, conversation_id, context_version)
    key = str(uuid.uuid4())
    confirm_body = {"version": proposal["version"], "context_version": context_version,
                    "idempotency_key": key}
    from app.db.session import SessionLocal
    from app.models.entities import GlucoseRecord, GlucoseRecordSource, ProvenanceEvent
    from app.models.glico import GlicoExecution, GlicoProposal
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(GlucoseRecord).where(GlucoseRecord.patient_id == patient.id))
    first = patient.client.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers, json=confirm_body)
    assert first.status_code == 200, first.text
    receipt = first.json()["receipt"]
    second = patient.client.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers, json=confirm_body)
    assert second.status_code == 200, second.text
    assert second.json()["receipt"] == receipt
    replay_with_new_key = patient.client.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers,
        json={**confirm_body, "idempotency_key": str(uuid.uuid4())})
    assert replay_with_new_key.status_code == 200, replay_with_new_key.text
    assert replay_with_new_key.json()["receipt"] == receipt
    with SessionLocal() as db:
        after = db.scalar(select(func.count()).select_from(GlucoseRecord).where(GlucoseRecord.patient_id == patient.id))
        assert after == before + 1
        assert db.scalar(select(func.count()).select_from(GlucoseRecordSource).where(
            GlucoseRecordSource.glucose_record_id == receipt["result_id"])) == 1
        assert db.scalar(select(func.count()).select_from(GlicoExecution).where(
            GlicoExecution.proposal_id == proposal["id"])) == 1
        stored = db.get(GlicoProposal, proposal["id"])
        assert stored.state == "EXECUTED"
        assert stored.payload_encrypted == b""
    changed = patient.client.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers,
        json={**confirm_body, "version": proposal["version"] + 1})
    assert changed.status_code == 409


def test_glico_concurrent_confirmations_create_one_effect(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, context_version = _conversation(patient, headers)
    proposal = _draft(patient, headers, conversation_id, context_version)
    def confirm():
        return patient.client.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers,
            json={"version": proposal["version"], "context_version": context_version,
                  "idempotency_key": str(uuid.uuid4())})
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: confirm(), range(10)))
    assert all(result.status_code == 200 for result in results), [
        (result.status_code, result.json()) for result in results]
    assert all(result.json()["receipt"] == results[0].json()["receipt"] for result in results)
    from app.db.session import SessionLocal
    from app.models.entities import GlucoseRecord
    from app.models.glico import GlicoExecution
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GlicoExecution).where(
            GlicoExecution.proposal_id == proposal["id"])) == 1
        assert db.scalar(select(func.count()).select_from(GlucoseRecord).where(
            GlucoseRecord.patient_id == patient.id)) == 1


def test_glico_idempotency_key_cannot_be_reused_for_another_proposal(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, context_version = _conversation(patient, headers)
    first = _draft(patient, headers, conversation_id, context_version)
    shared_key = str(uuid.uuid4())
    first_result = patient.client.post(f"/api/glico/proposals/{first['id']}/confirm", headers=headers,
        json={"version": first["version"], "context_version": context_version, "idempotency_key": shared_key})
    assert first_result.status_code == 200, first_result.text

    second_response = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": "142 mg/dL", "context_version": context_version, "client_request_id": str(uuid.uuid4())})
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()["proposal"]
    edited = patient.client.patch(f"/api/glico/proposals/{second['id']}", headers=headers,
        json={"version": second["version"], "context_version": context_version,
              "fields": {"measured_at": "2026-10-13T09:00:00-03:00", "timezone": "America/Sao_Paulo"}})
    assert edited.status_code == 200, edited.text
    second = edited.json()["proposal"]
    result = patient.client.post(f"/api/glico/proposals/{second['id']}/confirm", headers=headers,
        json={"version": second["version"], "context_version": context_version, "idempotency_key": shared_key})
    assert result.status_code == 409
    assert result.json()["detail"] == "idempotency_conflict"


def test_doctor_cannot_reuse_glico_conversation_after_revoke_and_reassociation(world: World):
    doctor = world.doctor()
    patient = world.patient()
    old_link = world.active_link(patient, doctor)
    headers = _csrf(doctor)
    conversation_id, _ = _conversation(doctor, headers)
    selected = doctor.client.patch(f"/api/glico/conversations/{conversation_id}/context", headers=headers,
        json={"version": 1, "patient_id": patient.id})
    assert selected.status_code == 200, selected.text
    old_context_version = selected.json()["context_version"]

    revoked = doctor.client.post(f"/api/doctor-links/{old_link['id']}/revoke", json={"version": old_link["version"]})
    assert revoked.status_code == 200, revoked.text
    new_link = world.active_link(patient, doctor)
    assert new_link["id"] != old_link["id"]

    stale_read = doctor.client.get(f"/api/glico/conversations/{conversation_id}")
    assert stale_read.status_code == 404
    stale_message = doctor.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": "128 mg/dL", "context_version": old_context_version,
              "client_request_id": str(uuid.uuid4())})
    assert stale_message.status_code == 404


def test_glico_confirmation_rolls_back_record_source_event_receipt_on_failure(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, context_version = _conversation(patient, headers)
    proposal = _draft(patient, headers, conversation_id, context_version)
    body = {"version": proposal["version"], "context_version": context_version,
            "idempotency_key": str(uuid.uuid4())}
    from app.db.session import SessionLocal
    from app.models.entities import GlucoseRecord
    from app.models.glico import GlicoProposal, GlicoExecution
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(GlucoseRecord).where(GlucoseRecord.patient_id == patient.id))
    with world.failing_insert("provenance_events", "NEW.activity_type = 'glico_glucose_entry'"):
        response = patient.client.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers, json=body)
    assert response.status_code == 500
    with SessionLocal() as db:
        after = db.scalar(select(func.count()).select_from(GlucoseRecord).where(GlucoseRecord.patient_id == patient.id))
        stored = db.get(GlicoProposal, proposal["id"])
        assert after == before
        assert stored.state == "READY"
        assert db.scalar(select(func.count()).select_from(GlicoExecution).where(
            GlicoExecution.proposal_id == proposal["id"])) == 0


def test_doctor_must_select_currently_linked_patient(world: World):
    doctor = world.doctor()
    patient = world.patient()
    headers = _csrf(doctor)
    conversation_id, context_version = _conversation(doctor, headers)
    response = doctor.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": "128 mg/dL", "context_version": context_version,
              "client_request_id": str(uuid.uuid4())})
    assert response.status_code == 409
    rejected = doctor.client.patch(f"/api/glico/conversations/{conversation_id}/context", headers=headers,
        json={"version": context_version, "patient_id": patient.id})
    assert rejected.status_code == 404
    world.active_link(patient, doctor)
    selected = doctor.client.patch(f"/api/glico/conversations/{conversation_id}/context", headers=headers,
        json={"version": context_version, "patient_id": patient.id})
    assert selected.status_code == 200, selected.text
    assert selected.json()["context"]["patient_id"] == patient.id
    forbidden_entry = doctor.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": "128 mg/dL", "context_version": selected.json()["context_version"],
              "client_request_id": str(uuid.uuid4())})
    assert forbidden_entry.status_code == 403
    assert forbidden_entry.json()["detail"] == "operation_not_allowed"


def test_glico_faq_is_deterministic_and_proposal_edits_keep_immutable_revisions(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, context_version = _conversation(patient, headers)
    faq = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": "How do I add a reading?", "context_version": context_version,
              "client_request_id": str(uuid.uuid4())})
    assert faq.status_code == 200
    assert faq.json()["type"] == "help"
    assert faq.json()["answer"]
    draft = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": "128 mg/dL", "context_version": context_version,
              "client_request_id": str(uuid.uuid4())}).json()["proposal"]
    edited = patient.client.patch(f"/api/glico/proposals/{draft['id']}", headers=headers,
        json={"version": draft["version"], "context_version": context_version,
              "fields": {"measured_at": "2026-10-13T08:00:00-03:00", "timezone": "America/Sao_Paulo"}})
    assert edited.status_code == 200, edited.text
    from app.db.session import SessionLocal
    from app.models.glico import GlicoProposalRevision
    with SessionLocal() as db:
        revisions = db.scalars(select(GlicoProposalRevision).where(
            GlicoProposalRevision.proposal_id == draft["id"]).order_by(GlicoProposalRevision.version)).all()
        assert [row.version for row in revisions] == [1, 2]
        assert revisions[0].digest != revisions[1].digest


def test_glico_duplicate_measurement_numbers_and_hi_lo_never_auto_propose(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, context_version = _conversation(patient, headers)
    for text in ("meter shows 128 and 132 mg/dL", "HI mg/dL"):
        response = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
            json={"text": text, "context_version": context_version, "client_request_id": str(uuid.uuid4())})
        assert response.status_code == 200, response.text
        assert response.json()["type"] == "clarification"


def test_patient_investigation_is_only_created_after_reviewed_glico_confirmation(world: World):
    patient = world.patient()
    doctor = world.doctor()
    world.active_link(patient, doctor)
    headers = _csrf(patient)
    conversation_id, _ = _conversation(patient, headers)
    selected = patient.client.patch(f"/api/glico/conversations/{conversation_id}/context", headers=headers,
        json={"version": 1, "doctor_id": doctor.id})
    assert selected.status_code == 200, selected.text
    context_version = selected.json()["context_version"]
    proposed = patient.client.post(f"/api/glico/conversations/{conversation_id}/collaboration-proposals",
        headers=headers, json={"kind": "investigation_open", "title": "Review readings",
                               "content": "Please review the selected readings."})
    assert proposed.status_code == 201, proposed.text
    proposal = proposed.json()["proposal"]
    assert proposal["state"] == "READY"
    from app.db.session import SessionLocal
    from app.models.entities import Investigation, InvestigationMessage
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Investigation).where(
            Investigation.patient_id == patient.id)) == 0
    confirmed = patient.client.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers,
        json={"version": proposal["version"], "context_version": context_version,
              "idempotency_key": str(uuid.uuid4())})
    assert confirmed.status_code == 200, confirmed.text
    receipt = confirmed.json()["receipt"]
    assert receipt["result_type"] == "investigation"
    with SessionLocal() as db:
        item = db.get(Investigation, receipt["result_id"])
        messages = db.scalars(select(InvestigationMessage).where(
            InvestigationMessage.investigation_id == receipt["result_id"])).all()
        assert item is not None and item.patient_id == patient.id and item.doctor_id == doctor.id
        assert len(messages) == 1
    reply = patient.client.post(f"/api/glico/conversations/{conversation_id}/collaboration-proposals",
        headers=headers, json={"kind": "investigation_message", "investigation_id": receipt["result_id"],
                               "content": "Additional context for review."})
    assert reply.status_code == 201, reply.text
    reply_proposal = reply.json()["proposal"]
    edited = patient.client.patch(f"/api/glico/proposals/{reply_proposal['id']}", headers=headers,
        json={"version": reply_proposal["version"], "context_version": context_version,
              "fields": {"content": "Revised content for review."}})
    assert edited.status_code == 200, edited.text
    sent = patient.client.post(f"/api/glico/proposals/{reply_proposal['id']}/confirm", headers=headers,
        json={"version": edited.json()["proposal"]["version"], "context_version": context_version,
              "idempotency_key": str(uuid.uuid4())})
    assert sent.status_code == 200, sent.text
    assert sent.json()["receipt"]["result_type"] == "investigation_message"
    with SessionLocal() as db:
        messages = db.scalars(select(InvestigationMessage).where(
            InvestigationMessage.investigation_id == receipt["result_id"])).all()
        assert len(messages) == 2


def test_glico_read_query_is_backend_sourced_and_respects_selected_period(world: World):
    patient = world.patient()
    now = datetime.now(timezone.utc)
    added = patient.client.post(f"/api/patients/{patient.id}/glucose-records", json={
        "measured_at": now.isoformat(), "glucose_mg_dl": 126.0,
    })
    assert added.status_code == 201, added.text
    headers = _csrf(patient)
    created = patient.client.post("/api/glico/conversations", headers=headers,
        json={"locale": "en-US", "client_request_id": str(uuid.uuid4())})
    conversation_id = created.json()["id"]
    from app.core.patient_time import patient_local_datetime
    from app.db.session import SessionLocal
    from app.models.entities import Patient
    with SessionLocal() as db:
        timezone_name = db.get(Patient, patient.id).timezone
    selected_day = patient_local_datetime(now.replace(tzinfo=None), timezone_name).date().isoformat()
    context = patient.client.patch(f"/api/glico/conversations/{conversation_id}/context", headers=headers,
        json={"version": 1, "period_start": selected_day, "period_end": selected_day})
    assert context.status_code == 200, context.text
    result = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": "Show readings", "context_version": context.json()["context_version"],
              "client_request_id": str(uuid.uuid4())})
    assert result.status_code == 200, result.text
    assert result.json()["type"] == "answer"
    assert any(row["glucose_mg_dl"] == 126.0 for row in result.json()["items"])


@pytest.mark.parametrize("lang", ["pt-BR", "en-US", "es"])
def test_patient_pdf_endpoint_accepts_contract_period_and_locales(world: World, lang):
    patient = world.patient()
    response = patient.client.get(f"/api/patients/{patient.id}/report.pdf", params={
        "start_date": "2026-10-01", "end_date": "2026-10-13", "lang": lang})
    assert response.status_code == 200, response.text[:200]
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["cache-control"] == "no-store, private"
    assert response.content.startswith(b"%PDF-")


def test_message_request_replay_is_cached_and_does_not_consume_quota(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    request_id = str(uuid.uuid4())
    body = {"text": "How do I add a reading?", "context_version": version,
            "client_request_id": request_id}
    first = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers, json=body)
    assert first.status_code == 200, first.text
    from app.db.session import SessionLocal
    from app.models.glico import GlicoQuotaBucket
    with SessionLocal() as db:
        before = sum(db.scalars(select(GlicoQuotaBucket.used).where(
            GlicoQuotaBucket.owner_account_id == world.account_id(patient),
            GlicoQuotaBucket.bucket == "messages_minute")).all())
    repeated = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers, json=body)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == first.json()
    altered = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={**body, "text": "How do I get a PDF report?"})
    assert altered.status_code == 409
    from app.models.glico import GlicoRequestReplay
    with SessionLocal() as db:
        receipt = db.scalar(select(GlicoRequestReplay).where(
            GlicoRequestReplay.owner_account_id == world.account_id(patient),
            GlicoRequestReplay.client_request_id == request_id))
        receipt.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    expired_retry = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={**body, "text": "How do I get a PDF report?"})
    assert expired_retry.status_code == 200, expired_retry.text
    assert expired_retry.json()["type"] == "help"
    with SessionLocal() as db:
        after = sum(db.scalars(select(GlicoQuotaBucket.used).where(
            GlicoQuotaBucket.owner_account_id == world.account_id(patient),
            GlicoQuotaBucket.bucket == "messages_minute")).all())
    assert after == before + 1  # one additional, distinct request after the replay receipt TTL


def test_media_requires_context_and_request_headers_and_rechecks_worker_snapshot(world: World, monkeypatch):
    from types import SimpleNamespace
    from app.api import glico_routes
    from app.db.session import SessionLocal
    from app.models.glico import GlicoConversation, GlicoProposal

    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    monkeypatch.setattr(glico_routes, "get_settings", lambda: SimpleNamespace(
        glico_enabled=True, glico_audio_enabled=True, glico_photo_enabled=True,
        glico_media_global_jobs=2, glico_media_worker_url="http://worker",
        glico_media_worker_secret="s" * 32))
    url = f"/api/glico/conversations/{conversation_id}/extract/audio"
    base = {**headers, "content-type": "application/octet-stream"}
    unsupported = patient.client.post(url, headers={**headers, "content-type": "image/png",
        "x-glico-context-version": str(version), "x-glico-request-id": str(uuid.uuid4())}, content=b"x")
    assert unsupported.status_code == 415
    too_large = patient.client.post(url, headers={**base, "x-glico-context-version": str(version),
        "x-glico-request-id": str(uuid.uuid4())}, content=b"x" * (3 * 1024 * 1024 + 1))
    assert too_large.status_code == 413
    missing = patient.client.post(url, headers=base, content=b"attacker bytes")
    assert missing.status_code == 422
    stale = patient.client.post(url, headers={**base, "x-glico-context-version": str(version - 1),
        "x-glico-request-id": str(uuid.uuid4())}, content=b"attacker bytes")
    assert stale.status_code == 409
    bad_id = patient.client.post(url, headers={**base, "x-glico-context-version": str(version),
        "x-glico-request-id": "not-a-uuid"}, content=b"attacker bytes")
    assert bad_id.status_code == 422

    class FakeResponse:
        status_code = 200
        async def __aenter__(self):
            with SessionLocal() as db:
                item = db.get(GlicoConversation, conversation_id)
                item.context_version += 1
                db.commit()
            return self
        async def __aexit__(self, *args):
            return False
        async def aiter_bytes(self):
            yield b'{"text":"128 mg/dL","language":"en","engine":"test"}'

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def stream(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(glico_routes.httpx, "AsyncClient", FakeClient)
    result = patient.client.post(url, headers={**base, "x-glico-context-version": str(version),
        "x-glico-request-id": str(uuid.uuid4())}, content=b"opaque audio bytes")
    assert result.status_code == 409, result.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GlicoProposal).where(
            GlicoProposal.conversation_id == conversation_id)) == 0


def test_glico_proposal_ttl_expires_confirmation(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    proposal = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": "128 mg/dL", "context_version": version,
              "client_request_id": str(uuid.uuid4())}).json()["proposal"]
    from app.db.session import SessionLocal
    from app.models.glico import GlicoProposal
    with SessionLocal() as db:
        row = db.get(GlicoProposal, proposal["id"])
        row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    response = patient.client.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers,
        json={"version": proposal["version"], "context_version": version,
              "idempotency_key": str(uuid.uuid4())})
    assert response.status_code == 410


def test_audio_gateway_creates_reviewed_proposal_without_echo_and_replays(world: World, monkeypatch):
    from types import SimpleNamespace
    import hashlib
    import hmac
    import time
    from app.api import glico_routes
    from app.db.session import SessionLocal
    from app.models.glico import GlicoProposal

    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    secret = "a" * 32
    monkeypatch.setattr(glico_routes, "get_settings", lambda: SimpleNamespace(
        glico_enabled=True, glico_audio_enabled=True, glico_photo_enabled=False,
        glico_media_global_jobs=2, glico_media_worker_url="http://worker",
        glico_media_worker_secret=secret))
    calls = []

    class FakeResponse:
        status_code = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def aiter_bytes(self):
            yield b'{"text":"128 mg/dL","language":"en","engine":"fake-asr","assessment":{"status":"review_required","needs_clarification":false,"clarification_reasons":[],"candidate_value_mg_dl":128,"candidate_confidence":0.9,"confidence_threshold":0.55}}'

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def stream(self, method, url, *, content, headers):
            calls.append((method, url))
            assert method == "POST" and url.endswith("/internal/extract/audio")
            digest = hashlib.sha256(content).hexdigest()
            assert headers["x-worker-content-sha256"] == digest
            signed = "\n".join((method, "/internal/extract/audio", headers["x-worker-timestamp"],
                                 headers["x-worker-nonce"], digest)).encode("ascii")
            expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
            assert hmac.compare_digest(headers["x-worker-signature"], expected)
            assert abs(int(time.time()) - int(headers["x-worker-timestamp"])) <= 2
            return FakeResponse()

    monkeypatch.setattr(glico_routes.httpx, "AsyncClient", FakeClient)
    request_id = str(uuid.uuid4())
    upload_headers = {**headers, "content-type": "application/octet-stream",
        "x-glico-context-version": str(version), "x-glico-request-id": request_id}
    first = patient.client.post(f"/api/glico/conversations/{conversation_id}/extract/audio",
                                headers=upload_headers, content=b"fake audio container")
    assert first.status_code == 200, first.text
    assert first.json()["type"] == "proposal"
    assert first.json()["proposal"]["origin"] == "glico_audio"
    assert "text" not in first.json()
    replay = patient.client.post(f"/api/glico/conversations/{conversation_id}/extract/audio",
                                 headers=upload_headers, content=b"fake audio container")
    assert replay.status_code == 200 and replay.json() == first.json()
    assert len(calls) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GlicoProposal).where(
            GlicoProposal.conversation_id == conversation_id)) == 1


def _worker_assessment(value=128, confidence=0.95, threshold=0.75, *, needs_clarification=False,
                       reasons=None):
    return {"status": "needs_clarification" if needs_clarification else "review_required",
            "needs_clarification": needs_clarification,
            "clarification_reasons": reasons or [],
            "candidate_value_mg_dl": None if needs_clarification else value,
            "candidate_confidence": confidence,
            "confidence_threshold": threshold,
            "physiological_range_mg_dl": [20, 600]}


@pytest.mark.parametrize("media_kind", ["image", "audio"])
@pytest.mark.parametrize("outcome", ["success", "error", "timeout", "cancel"])
def test_media_job_reservation_is_released_on_every_exit(world: World, monkeypatch, media_kind, outcome):
    import asyncio
    import json
    from types import SimpleNamespace
    from app.api import glico_routes
    from app.db.session import SessionLocal
    from app.models.glico import GlicoGlobalQuota, GlicoQuotaBucket

    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    monkeypatch.setattr(glico_routes, "get_settings", lambda: SimpleNamespace(
        glico_enabled=True, glico_audio_enabled=True, glico_photo_enabled=True,
        glico_media_global_jobs=2, glico_media_worker_url="http://worker",
        glico_media_worker_secret="m" * 32))

    payload = ({"text": "128 mg/dL", "language": "en", "engine": "fake-asr",
                "assessment": _worker_assessment(threshold=0.55)} if media_kind == "audio" else
               {"engine": "fake-ocr", "candidates": [{"text": "128 mg/dL", "confidence": 0.95}],
                "assessment": _worker_assessment()})

    class FakeResponse:
        def __init__(self):
            self.status_code = 500 if outcome == "error" else 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def aiter_bytes(self):
            if outcome == "cancel":
                raise asyncio.CancelledError()
            yield json.dumps(payload).encode()

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def stream(self, *args, **kwargs):
            if outcome == "timeout":
                class TimedOut:
                    async def __aenter__(self): raise glico_routes.httpx.ReadTimeout("timeout")
                    async def __aexit__(self, *args): return False
                return TimedOut()
            return FakeResponse()

    monkeypatch.setattr(glico_routes.httpx, "AsyncClient", FakeClient)
    url = f"/api/glico/conversations/{conversation_id}/extract/{media_kind}"
    upload_headers = {**headers, "content-type": "application/octet-stream",
        "x-glico-context-version": str(version), "x-glico-request-id": str(uuid.uuid4())}
    if outcome == "cancel":
        response = patient.client.post(url, headers=upload_headers, content=b"synthetic media")
        assert response.status_code >= 500
    else:
        response = patient.client.post(url, headers=upload_headers, content=b"synthetic media")
        assert response.status_code == (200 if outcome == "success" else 503 if outcome == "error" else 504), response.text
        if outcome == "success":
            assert response.json()["type"] == "proposal"

    marker = datetime(2000, 1, 1)
    with SessionLocal() as db:
        global_row = db.get(GlicoGlobalQuota, media_kind)
        assert global_row.reserved == 0
        active = db.scalar(select(GlicoQuotaBucket).where(
            GlicoQuotaBucket.owner_account_id == world.account_id(patient),
            GlicoQuotaBucket.bucket == f"{media_kind}_active",
            GlicoQuotaBucket.window_start == marker))
        assert active is None or active.reserved == 0
        other_global = db.get(GlicoGlobalQuota, "audio" if media_kind == "image" else "image")
        assert other_global.reserved == 0


@pytest.mark.skipif(IS_SQLITE, reason="shared row-lock quota serialization requires MySQL")
def test_global_media_quota_serializes_concurrent_accounts(world: World):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi import HTTPException
    from app.db.session import SessionLocal
    from app.models.glico import GlicoGlobalQuota
    from app.services.glico import release_media_job, reserve_media_job

    owners = [world.account_id(world.patient()) for _ in range(8)]
    with SessionLocal() as db:
        assert db.get(GlicoGlobalQuota, "image").reserved == 0

    def reserve(owner_id):
        with SessionLocal() as db:
            try:
                reserve_media_job(db, owner_id, "image", global_limit=1)
                db.commit()
                return "reserved"
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(reserve, owners))
    assert outcomes.count("reserved") == 1, outcomes
    assert outcomes.count(429) == 7, outcomes
    with SessionLocal() as db:
        row = db.get(GlicoGlobalQuota, "image")
        assert row.reserved == 1
        release_media_job(db, owners[outcomes.index("reserved")], "image")
        db.commit()
    with SessionLocal() as db:
        assert db.get(GlicoGlobalQuota, "image").reserved == 0


@pytest.mark.parametrize("value", [19, 601])
def test_text_readings_outside_physiological_range_only_clarify(world: World, value):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    response = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": f"{value} mg/dL 2026-10-13 08:30", "context_version": version,
              "client_request_id": str(uuid.uuid4())})
    assert response.status_code == 200, response.text
    assert response.json() == {"type": "clarification", "answer_key": "glico.reading.out_of_range"}


@pytest.mark.parametrize("media_kind", ["image", "audio"])
@pytest.mark.parametrize("assessment", [
    _worker_assessment(128, needs_clarification=True, reasons=["unit_missing"]),
    _worker_assessment(128, confidence=0.4, threshold=0.75),
    _worker_assessment(601, confidence=0.99, threshold=0.75),
    {"status": "needs_clarification", "needs_clarification": True,
     "clarification_reasons": ["multiple_candidates"], "candidate_value_mg_dl": None,
     "candidate_confidence": 0.99, "confidence_threshold": 0.75},
])
def test_worker_ambiguous_untrusted_or_out_of_range_never_creates_proposal(
        world: World, monkeypatch, media_kind, assessment):
    import json
    from types import SimpleNamespace
    from app.api import glico_routes
    from app.db.session import SessionLocal
    from app.models.glico import GlicoProposal

    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    monkeypatch.setattr(glico_routes, "get_settings", lambda: SimpleNamespace(
        glico_enabled=True, glico_audio_enabled=True, glico_photo_enabled=True,
        glico_media_global_jobs=2, glico_media_worker_url="http://worker",
        glico_media_worker_secret="a" * 32))
    payload = ({"text": "128 mg/dL", "language": "en", "engine": "fake-asr", "assessment": assessment}
               if media_kind == "audio" else
               {"candidates": [{"text": "128 mg/dL", "confidence": 0.99}],
                "engine": "fake-ocr", "assessment": assessment})

    class FakeResponse:
        status_code = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def aiter_bytes(self): yield json.dumps(payload).encode()
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def stream(self, *args, **kwargs): return FakeResponse()
    monkeypatch.setattr(glico_routes.httpx, "AsyncClient", FakeClient)
    response = patient.client.post(
        f"/api/glico/conversations/{conversation_id}/extract/{media_kind}",
        headers={**headers, "content-type": "application/octet-stream",
            "x-glico-context-version": str(version), "x-glico-request-id": str(uuid.uuid4())},
        content=b"synthetic media")
    assert response.status_code == 200, response.text
    assert response.json()["type"] == "clarification"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GlicoProposal).where(
            GlicoProposal.conversation_id == conversation_id)) == 0


def test_confirm_and_edit_reject_glucose_outside_physiological_range(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    proposal = patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": "128 mg/dL", "context_version": version,
              "client_request_id": str(uuid.uuid4())}).json()["proposal"]
    edit = patient.client.patch(f"/api/glico/proposals/{proposal['id']}", headers=headers,
        json={"version": proposal["version"], "context_version": version,
              "fields": {"glucose_mg_dl": 601, "measured_at": "2026-10-13T08:30:00-03:00"}})
    assert edit.status_code == 422
    ready = patient.client.patch(f"/api/glico/proposals/{proposal['id']}", headers=headers,
        json={"version": proposal["version"], "context_version": version,
              "fields": {"glucose_mg_dl": 128, "measured_at": "2026-10-13T08:30:00-03:00",
                         "timezone": "America/Sao_Paulo"}})
    assert ready.status_code == 200 and ready.json()["proposal"]["state"] == "READY"

    from app.db.session import SessionLocal
    from app.core.crypto import decrypt_field, encrypt_field
    from app.models.glico import GlicoProposal
    import json
    with SessionLocal() as db:
        row = db.get(GlicoProposal, proposal["id"])
        decoded = json.loads(decrypt_field(row.payload_encrypted, table="glico_proposals",
            column="payload", record_id=row.id))
        decoded["fields"]["glucose_mg_dl"] = 601
        row.payload_encrypted = encrypt_field(json.dumps(decoded), table="glico_proposals",
            column="payload", record_id=row.id)
        db.commit()
    confirm = patient.client.post(f"/api/glico/proposals/{proposal['id']}/confirm", headers=headers,
        json={"version": ready.json()["proposal"]["version"], "context_version": version,
              "idempotency_key": str(uuid.uuid4())})
    assert confirm.status_code == 422


def test_expired_replay_rows_are_cleaned_and_keys_reusable(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    from app.db.session import SessionLocal
    from app.models.glico import GlicoRequestReplay
    from app.services.glico import cleanup_expired_glico_replays
    now = datetime.utcnow()
    expired_id, live_id = str(uuid.uuid4()), str(uuid.uuid4())
    with SessionLocal() as db:
        db.add_all([
            GlicoRequestReplay(id=expired_id, conversation_id=conversation_id, owner_account_id=world.account_id(patient),
                operation="message", client_request_id=str(uuid.uuid4()), request_digest="0" * 64,
                response_encrypted=b"expired", expires_at=now - timedelta(seconds=1)),
            GlicoRequestReplay(id=live_id, conversation_id=conversation_id, owner_account_id=world.account_id(patient),
                operation="message", client_request_id=str(uuid.uuid4()), request_digest="1" * 64,
                response_encrypted=b"live", expires_at=now + timedelta(hours=1)),
        ])
        db.commit()
        assert cleanup_expired_glico_replays(db, now=now) == 1
        db.commit()
        assert db.get(GlicoRequestReplay, expired_id) is None
        assert db.get(GlicoRequestReplay, live_id).response_encrypted == b"live"


def test_worker_hmac_replay_store_is_atomic_under_concurrency_and_expires():
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from app.media_worker.auth import sign_request, verify_request

    class MemoryReplayStore:
        def __init__(self):
            self.entries = {}
            self.lock = threading.Lock()
        def consume_once(self, nonce, expires_at):
            now = int(time.time())
            with self.lock:
                self.entries = {key: expiry for key, expiry in self.entries.items() if expiry > now}
                if nonce in self.entries:
                    return False
                self.entries[nonce] = expires_at
                return True

    secret = b"r" * 32
    body = b"synthetic bounded payload"
    issued = int(time.time())
    nonce = "A" * 32
    signature = sign_request(secret, "POST", "/internal/extract/image", str(issued), nonce, body)
    store = MemoryReplayStore()
    def attempt(_):
        return verify_request(secret, "POST", "/internal/extract/image", body, signature, store,
                              now=issued, max_skew_seconds=2)
    with ThreadPoolExecutor(max_workers=16) as pool:
        accepted = list(pool.map(attempt, range(16)))
    assert sum(accepted) == 1
    assert len(store.entries) == 1
    with store.lock:
        store.entries[nonce] = issued - 1
    fresh = sign_request(secret, "POST", "/internal/extract/image", str(issued + 3), nonce, body)
    assert verify_request(secret, "POST", "/internal/extract/image", body, fresh, store,
                          now=issued + 3, max_skew_seconds=2)
    assert len(store.entries) == 1


@pytest.mark.parametrize("signal", ["HI", "lo"])
def test_photo_with_meter_hi_lo_signal_is_never_recorded(world: World, monkeypatch, signal):
    import json
    from types import SimpleNamespace
    from app.api import glico_routes

    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    monkeypatch.setattr(glico_routes, "get_settings", lambda: SimpleNamespace(
        glico_enabled=True, glico_audio_enabled=True, glico_photo_enabled=True,
        glico_media_global_jobs=2, glico_media_worker_url="http://worker",
        glico_media_worker_secret="m" * 32))
    payload = {"engine": "fake-ocr", "candidates": [{"text": signal, "confidence": 0.97},
               {"text": "mg/dL", "confidence": 0.95}],
               "assessment": _worker_assessment(needs_clarification=True, reasons=["value_not_detected"])}

    class FakeResponse:
        status_code = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def aiter_bytes(self):
            yield json.dumps(payload).encode()

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def stream(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(glico_routes.httpx, "AsyncClient", FakeClient)
    response = patient.client.post(
        f"/api/glico/conversations/{conversation_id}/extract/image",
        headers={**headers, "content-type": "application/octet-stream",
                 "x-glico-context-version": str(version), "x-glico-request-id": str(uuid.uuid4())},
        content=b"synthetic media")
    assert response.status_code == 200, response.text
    assert response.json() == {"type": "clarification", "answer_key": "glico.reading.unsupported_signal"}


def _llm_settings():
    from types import SimpleNamespace
    return SimpleNamespace(
        glico_enabled=True, glico_audio_enabled=False, glico_photo_enabled=False, glico_media_global_jobs=0,
        glico_media_worker_url=None, glico_media_worker_secret=None,
        gemini_api_key="test-key", gemini_model="m", gemini_timeout_seconds=5)


def _post_text(patient, headers, conversation_id, version, text):
    return patient.client.post(f"/api/glico/conversations/{conversation_id}/messages", headers=headers,
        json={"text": text, "context_version": version, "client_request_id": str(uuid.uuid4()),
              "history": [{"role": "user", "text": "oi"}, {"role": "assistant", "text": "olá"}]})


@pytest.fixture
def llm(world: World, monkeypatch):
    from app.api import glico_routes
    from app.services import glico_llm
    answers: dict = {"next": None}
    monkeypatch.setattr(glico_routes, "get_settings", _llm_settings)
    monkeypatch.setattr(glico_llm, "interpret", lambda **kwargs: answers["next"])
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    return SimpleNamespaceBox(patient, headers, conversation_id, version, answers)


class SimpleNamespaceBox:
    def __init__(self, patient, headers, conversation_id, version, answers):
        self.patient, self.headers, self.conversation_id, self.version, self.answers = (
            patient, headers, conversation_id, version, answers)

    def say(self, text, intent):
        self.answers["next"] = intent
        return _post_text(self.patient, self.headers, self.conversation_id, self.version, text)


def test_model_reading_intent_still_ends_in_a_reviewable_proposal(llm):
    response = llm.say("minha glicose deu 132 hoje às 8h", {
        "intent": "record_reading", "glucose_value": 132.0, "unit": "mg/dL",
        "measured_date": "2026-10-14", "measured_time": "08:00", "reply": ""})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["type"] == "proposal" and body["proposal"]["fields"]["glucose_mg_dl"] == 132.0
    assert body["proposal"]["state"] in {"DRAFT", "READY"}


def test_model_cannot_invent_a_value_the_user_did_not_type(llm):
    response = llm.say("minha glicose deu 132", {
        "intent": "record_reading", "glucose_value": 150.0, "unit": "mg/dL", "reply": ""})
    assert response.status_code == 200
    assert response.json()["type"] != "proposal"


def test_model_reply_is_plain_text_and_failure_falls_back_to_keywords(llm):
    said = llm.say("oi, tudo bem?", {"intent": "answer", "reply": "Oi! Como posso ajudar?"})
    assert said.json() == {"type": "message", "text": "Oi! Como posso ajudar?"}
    fallback = llm.say("128 mg/dL", None)
    assert fallback.json()["type"] == "proposal"


def test_model_pdf_intent_and_capability_flag(llm):
    assert llm.say("quero o relatório", {"intent": "pdf_report", "reply": ""}).json() == {
        "type": "answer", "answer_key": "glico.query.pdf"}
    caps = llm.patient.client.get("/api/glico/capabilities")
    assert caps.json()["language_model"] is True and caps.json()["external_language_provider"] is True


def test_without_a_key_the_assistant_stays_deterministic(world: World):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    caps = patient.client.get("/api/glico/capabilities").json()
    assert caps["language_model"] is False and caps["external_language_provider"] is False
    response = _post_text(patient, headers, conversation_id, version, "128 mg/dL")
    assert response.json()["type"] == "proposal"


def test_dose_question_is_refused_even_if_the_model_misclassifies_it(llm):
    response = llm.say("tenho que tomar quantas unidades de insulina com 250?",
                       {"intent": "pdf_report", "reply": ""})
    body = response.json()
    assert body["type"] == "message" and "médico" in body["text"]


def test_off_topic_requests_get_a_fixed_reply_never_model_text(llm):
    body = llm.say("como escrevo hello world em python?",
                   {"intent": "off_topic", "reply": "print('Hello World')"}).json()
    assert body["type"] == "message"
    assert "print(" not in body["text"] and "MyGlico" in body["text"]


def test_spoken_number_words_become_a_reviewable_proposal_with_transcript(world: World, monkeypatch):
    import json
    from app.api import glico_routes
    from app.services import glico_llm

    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    settings = _llm_settings()
    settings.glico_audio_enabled = True
    settings.glico_media_global_jobs = 2
    settings.glico_media_worker_url = "http://worker"
    settings.glico_media_worker_secret = "m" * 32
    monkeypatch.setattr(glico_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(glico_llm, "interpret", lambda **kwargs: {
        "intent": "record_reading", "glucose_value": 128.0, "unit": "mg/dL", "reply": ""})
    spoken = "minha glicose está em cento e vinte e oito miligramas por decilitro"
    payload = {"text": spoken, "language": "pt", "engine": "fake-asr",
               "assessment": _worker_assessment(needs_clarification=True, reasons=["value_not_detected"])}

    class FakeResponse:
        status_code = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def aiter_bytes(self):
            yield json.dumps(payload).encode()

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def stream(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(glico_routes.httpx, "AsyncClient", FakeClient)
    response = patient.client.post(
        f"/api/glico/conversations/{conversation_id}/extract/audio",
        headers={**headers, "content-type": "application/octet-stream",
                 "x-glico-context-version": str(version), "x-glico-request-id": str(uuid.uuid4())},
        content=b"synthetic media")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["type"] == "proposal" and body["proposal"]["fields"]["glucose_mg_dl"] == 128.0
    assert body["proposal"]["origin"] == "glico_audio"
    assert body["transcript"] == spoken


@pytest.mark.parametrize("text", ["My glucose is 128 mg/dL", "minha glicemia deu 128 mg/dL", "mi glucosa es 128 mg/dL"])
def test_a_value_with_unit_is_recorded_not_treated_as_a_readings_query(world: World, text):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    response = _post_text(patient, headers, conversation_id, version, text)
    assert response.status_code == 200, response.text
    assert response.json()["type"] == "proposal"


def test_reading_without_date_defaults_to_now_and_says_so_while_a_stated_time_is_respected(world: World):
    from datetime import datetime, timedelta
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    assumed = _post_text(patient, headers, conversation_id, version, "glicemia 110 mg/dL").json()["proposal"]
    moment = datetime.fromisoformat(assumed["fields"]["measured_at"])
    assert abs(datetime.now(moment.tzinfo) - moment) < timedelta(minutes=2)
    assert assumed["state"] == "READY" and "measured_at_assumed" in assumed["warnings"]
    stated = _post_text(patient, headers, conversation_id, version, "glicemia 110 mg/dL 2026-10-13 8:05").json()["proposal"]
    assert stated["fields"]["measured_at"].startswith("2026-10-13T08:05")
    assert "measured_at_assumed" not in stated["warnings"]


def test_audio_gateway_sends_the_interface_language_hint_and_a_longer_deadline(world: World, monkeypatch):
    import json
    from types import SimpleNamespace
    from app.api import glico_routes

    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    monkeypatch.setattr(glico_routes, "get_settings", lambda: SimpleNamespace(
        glico_enabled=True, glico_audio_enabled=True, glico_photo_enabled=False, glico_media_global_jobs=2,
        glico_media_worker_url="http://worker", glico_media_worker_secret="m" * 32))
    seen = {}
    payload = {"text": "oi", "language": "pt", "engine": "fake-asr",
               "assessment": _worker_assessment(needs_clarification=True, reasons=["value_not_detected"])}

    class FakeResponse:
        status_code = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def aiter_bytes(self):
            yield json.dumps(payload).encode()

    class FakeClient:
        def __init__(self, *args, **kwargs): seen["timeout"] = kwargs.get("timeout")
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def stream(self, *args, **kwargs):
            seen["headers"] = kwargs.get("headers", {})
            return FakeResponse()

    monkeypatch.setattr(glico_routes.httpx, "AsyncClient", FakeClient)
    response = patient.client.post(
        f"/api/glico/conversations/{conversation_id}/extract/audio",
        headers={**headers, "content-type": "application/octet-stream",
                 "x-glico-context-version": str(version), "x-glico-request-id": str(uuid.uuid4())},
        content=b"synthetic media")
    assert response.status_code == 200, response.text
    assert seen["headers"]["x-glico-language"] == "pt"
    assert seen["timeout"].read == 48.0


def test_a_plain_value_with_unit_is_recorded_without_calling_the_language_model(llm, monkeypatch):
    from app.services import glico_llm

    def must_not_run(**kwargs):
        raise AssertionError("the model must not be consulted for an unambiguous reading")

    monkeypatch.setattr(glico_llm, "interpret", must_not_run)
    response = _post_text(llm.patient, llm.headers, llm.conversation_id, llm.version, "glicemia 110 mg/dL")
    assert response.json()["type"] == "proposal"
    # free language still goes to the model, and a dose question is never short-circuited into a reading
    monkeypatch.setattr(glico_llm, "interpret", lambda **kwargs: {"intent": "answer", "reply": "x"})
    dose = _post_text(llm.patient, llm.headers, llm.conversation_id, llm.version,
                      "tomo 250 mg/dL, quantas unidades de insulina?")
    assert dose.json()["type"] == "message" and "médico" in dose.json()["text"]


def test_audio_daily_limit_defaults_to_30_and_zero_disables_it(world: World):
    from app.core.config import Settings
    from app.db.session import SessionLocal
    from app.services.glico import reserve_media_job, release_media_job

    assert Settings().glico_audio_daily_limit == 30
    owner = world.account_id(world.patient())
    with SessionLocal() as db:
        for _ in range(35):  # well past the default of 30: 0 means unlimited
            reserve_media_job(db, owner, "audio", 100, daily_limit=0)
            release_media_job(db, owner, "audio")
        db.commit()


def test_a_positive_audio_daily_limit_is_enforced(world: World):
    from fastapi import HTTPException
    from app.db.session import SessionLocal
    from app.services.glico import reserve_media_job, release_media_job

    owner = world.account_id(world.patient())
    with SessionLocal() as db:
        for _ in range(3):
            reserve_media_job(db, owner, "audio", 100, daily_limit=3)
            release_media_job(db, owner, "audio")
        with pytest.raises(HTTPException) as caught:
            reserve_media_job(db, owner, "audio", 100, daily_limit=3)
        assert caught.value.status_code == 429
        db.rollback()


def test_forwarded_proto_is_ignored_unless_explicitly_trusted(world: World, monkeypatch):
    from app.services import glico

    patient = world.patient()
    headers = _csrf(patient)
    # The test client talks https://testserver; this mimics the reverse case (a proxy scheme that
    # differs from the app's), which only the explicit trust switch may reconcile.
    mismatch = {**headers, "origin": "http://testserver", "x-forwarded-proto": "http"}

    def attempt(extra=None):
        return patient.client.post("/api/glico/conversations", headers={**mismatch, **(extra or {})},
                                   json={"locale": "pt-BR", "client_request_id": str(uuid.uuid4())})

    refused = attempt()
    assert refused.status_code == 403 and refused.json()["detail"] == "csrf_failed"

    real = glico.get_settings
    monkeypatch.setattr(glico, "get_settings", lambda: _TrustingSettings(real()))
    assert attempt().status_code == 201
    # A cross-site origin is still refused even when forwarding is trusted.
    assert attempt({"origin": "http://evil.example"}).status_code == 403


class _TrustingSettings:
    """Real settings with the forwarded-proto switch turned on."""
    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return True if name == "trust_forwarded_proto" else getattr(self._real, name)


@pytest.mark.parametrize("text,mg_dl", [("53", 53.0), ("35", 35.0), (" 118. ", 118.0), ("5,6", 100.9)])
def test_a_bare_number_in_the_glucose_chat_is_a_reading_with_inferred_unit(world: World, text, mg_dl):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    body = _post_text(patient, headers, conversation_id, version, text).json()
    assert body["type"] == "proposal" and body["proposal"]["fields"]["glucose_mg_dl"] == mg_dl


@pytest.mark.parametrize("text", ["2", "700", "30 dias", "faz 30 dias", "1.2.3"])
def test_other_short_texts_are_not_turned_into_readings(world: World, text):
    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    assert _post_text(patient, headers, conversation_id, version, text).json()["type"] != "proposal"


def test_a_low_confidence_audio_reading_becomes_a_proposal_that_carries_the_warning(world: World, monkeypatch):
    import json
    from types import SimpleNamespace
    from app.api import glico_routes

    patient = world.patient()
    headers = _csrf(patient)
    conversation_id, version = _conversation(patient, headers)
    monkeypatch.setattr(glico_routes, "get_settings", lambda: SimpleNamespace(
        glico_enabled=True, glico_audio_enabled=True, glico_photo_enabled=False, glico_media_global_jobs=2,
        glico_media_worker_url="http://worker", glico_media_worker_secret="m" * 32))
    payload = {"text": "Fiz o teste de 84.", "language": "pt", "engine": "fake-asr", "assessment": {
        "status": "review_required", "needs_clarification": False, "clarification_reasons": [],
        "candidate_value_mg_dl": 84, "candidate_confidence": 0.34, "confidence_threshold": 0.25,
        "low_confidence": True, "candidate_original_value": 84, "candidate_unit": "mg/dL", "unit_inferred": True}}

    class FakeResponse:
        status_code = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def aiter_bytes(self):
            yield json.dumps(payload).encode()

    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def stream(self, *args, **kwargs): return FakeResponse()

    monkeypatch.setattr(glico_routes.httpx, "AsyncClient", FakeClient)
    response = patient.client.post(
        f"/api/glico/conversations/{conversation_id}/extract/audio",
        headers={**headers, "content-type": "application/octet-stream",
                 "x-glico-context-version": str(version), "x-glico-request-id": str(uuid.uuid4())},
        content=b"synthetic media")
    body = response.json()
    assert response.status_code == 200 and body["type"] == "proposal", body
    assert body["proposal"]["fields"]["glucose_mg_dl"] == 84.0
    assert "low_confidence" in body["proposal"]["warnings"]
