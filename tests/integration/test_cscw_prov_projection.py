"""PROV-O projection of the CSCW provenance events (audit finding P2-02).

Drives a real lifecycle through the API (link, investigation opened from an
atypical day with messages, read, closing, revocation with automatic closure,
prompt deferral, notification read, filtered detail access), projects it with
``app.services.cscw_provenance`` and checks PROV-O structure, stable IRIs,
absence of message/PII literals and the protected-output rules of the CLI.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import RDF

from conftest import REPO_ROOT, World

PROV = Namespace("http://www.w3.org/ns/prov#")
MYGV = Namespace("https://w3id.org/myglico/vocab/")
EX = Namespace("https://myglico.local/execution/")


def _load_cli():
    spec = importlib.util.spec_from_file_location("export_cscw_provenance", REPO_ROOT / "scripts" / "export_cscw_provenance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _drain_outbox_after_test():
    """Act as the notification consumer so this module leaves no PENDING rows behind.

    The session database is shared and the drain is batch-limited, so leftover
    rows from these notification-heavy scenarios would starve later outbox tests.
    """
    yield
    from app.db.session import SessionLocal
    from app.services.notification_outbox import drain_notification_outbox

    for _ in range(20):
        with SessionLocal() as db:
            result = drain_notification_outbox(db, limit=500)
        if not result.get("processed"):
            break


@pytest.fixture()
def scenario(world: World) -> dict:
    marker = uuid.uuid4().hex
    patient, prompts = world.atypical_patient(display_name=f"Paciente Sigiloso {marker[:6]}")
    doctor = world.doctor(display_name=f"Dra Sigilosa {marker[6:12]}")
    link = world.active_link(patient, doctor)
    indicator_id = prompts[0]["indicator_id"]

    title = f"Titulo confidencial {marker}"
    first_message = f"Mensagem clinica secreta {marker}"
    reply = f"Resposta medica secreta {marker}"
    observation = f"Observacao de encerramento {marker}"
    reason = f"Motivo de revogacao {marker}"

    assert patient.client.post(f"/api/atypical-day-prompts/{indicator_id}/defer").status_code == 200
    investigation = world.open_investigation(patient, doctor, event_id=indicator_id, title=title, message=first_message)
    assert doctor.client.post(f"/api/investigations/{investigation['id']}/messages",
                              json={"content": reply}).status_code == 201
    assert patient.client.post(f"/api/investigations/{investigation['id']}/read",
                               json={"up_to_sequence": 2}).status_code == 200
    closed = patient.client.post(f"/api/investigations/{investigation['id']}/close",
                                 json={"version": 2, "observation": observation})
    assert closed.status_code == 200, closed.text
    still_open = world.open_investigation(doctor, patient, title=f"{title} 2", message=f"{first_message} 2")
    note = doctor.client.get("/api/notifications").json()["notifications"][0]
    assert doctor.client.post(f"/api/notifications/{note['id']}/read").status_code == 200
    assert doctor.client.get(f"/api/patients/{patient.id}/atypical-days",
                             params={"start_date": "2026-06-01", "end_date": "2026-06-10"}).status_code == 200
    revoked = patient.client.post(f"/api/doctor-links/{link['id']}/revoke",
                                  json={"version": link["version"], "reason": reason})
    assert revoked.status_code == 200, revoked.text

    return {
        "patient": patient, "doctor": doctor, "link": link, "indicator_id": indicator_id,
        "investigation": investigation, "still_open": still_open, "note": note,
        "secrets": [title, first_message, reply, observation, reason, patient.display_name,
                    doctor.display_name, patient.email, doctor.email, patient.short_id,
                    doctor.short_id, doctor.crm, patient.password, doctor.password,
                    world.account_id(patient), world.account_id(doctor)],
    }


def _project(patient_id: str) -> tuple[str, str, Graph]:
    from app.db.session import SessionLocal
    from app.services.cscw_provenance import build_cscw_prov_document, serialize_cscw_prov

    with SessionLocal() as db:
        document = build_cscw_prov_document(db, patient_id=patient_id)
    json_text, turtle = serialize_cscw_prov(document)
    graph = Graph()
    graph.parse(data=turtle, format="turtle")
    return json_text, turtle, graph


def _res(path: str) -> URIRef:
    from app.core.config import get_settings

    return URIRef(f"{get_settings().semantic_base_uri}{path}")


def _activity(event) -> URIRef:
    return _res(f"prov-event/{event.id}")


def test_projection_maps_cscw_events_to_prov_o(scenario: dict, world: World):
    from app.services.cscw_provenance import agent_pseudonym

    patient, doctor = scenario["patient"], scenario["doctor"]
    link_id, inv_id = scenario["link"]["id"], scenario["investigation"]["id"]
    _json, _ttl, g = _project(patient.id)

    # Every CSCW event of this patient became a typed prov:Activity.
    for activity in ("AssociationRequested", "AssociationConfirmed", "AssociationRevoked",
                     "InvestigationOpened", "InvestigationMessageAdded", "InvestigationReadAdvanced",
                     "InvestigationClosed", "InvestigationClosedByAssociationRevocation",
                     "AtypicalDayInvestigationPromptDeferred", "NotificationCreated", "NotificationRead",
                     "AtypicalDayDetailViewed", "PatientDetailFilterApplied"):
        events = [e for e in world.events(activity)
                  if (g.value(_activity(e), RDF.type) is not None)]
        assert events, f"{activity} not projected"
        for event in events:
            node = _activity(event)
            assert (node, RDF.type, PROV.Activity) in g
            assert (node, RDF.type, MYGV.CollaborationActivity) in g
            assert (node, MYGV.activityType, None) in g

    # Human agents are pseudonymous, carry the domain role and nothing else.
    patient_agent = _res(f"agent/{agent_pseudonym(world.account_id(patient))}")
    doctor_agent = _res(f"agent/{agent_pseudonym(world.account_id(doctor))}")
    assert (patient_agent, RDF.type, PROV.Agent) in g
    assert str(g.value(patient_agent, MYGV.domainRole)) == "patient"
    assert str(g.value(doctor_agent, MYGV.domainRole)) == "doctor"
    assert {p for p, _o in g.predicate_objects(patient_agent)} == {RDF.type, MYGV.domainRole}

    # Software agents (system notification/closure and analytics prompt).
    collaboration = EX["myglico-collaboration-service"]
    assert (collaboration, RDF.type, PROV.SoftwareAgent) in g

    # Association versions: v1 -> v2 (confirm, doctor) -> v3 (revoke, patient).
    link_v = {n: _res(f"patient-doctor-link/{link_id}/v{n}") for n in (1, 2, 3)}
    (confirm,) = world.events("AssociationConfirmed", link_id)
    (revoke,) = world.events("AssociationRevoked", link_id)
    assert (_activity(confirm), PROV.used, link_v[1]) in g
    assert (link_v[2], PROV.wasGeneratedBy, _activity(confirm)) in g
    assert (link_v[2], PROV.wasRevisionOf, link_v[1]) in g
    assert (link_v[2], PROV.wasAttributedTo, doctor_agent) in g
    assert (_activity(confirm), PROV.wasAssociatedWith, doctor_agent) in g
    assert (link_v[3], PROV.wasRevisionOf, link_v[2]) in g
    assert (_activity(revoke), PROV.wasAssociatedWith, patient_agent) in g
    assert (link_v[3], RDF.type, MYGV.PatientDoctorAssociation) in g
    assert (link_v[3], PROV.specializationOf, _res(f"patient-doctor-link/{link_id}")) in g
    assert str(g.value(link_v[3], MYGV.lifecycleStatus)) == "REVOKED"

    # Investigation opened from an atypical day: used + domain relation.
    inv = _res(f"investigation/{inv_id}")
    indicator = _res(f"daily-indicator/{scenario['indicator_id']}")
    (opened,) = world.events("InvestigationOpened", inv_id)
    assert (_activity(opened), PROV.used, indicator) in g
    assert (_activity(opened), PROV.used, link_v[2]) in g
    assert (inv, MYGV.investigatesAtypicalDay, indicator) in g
    assert (inv, MYGV.underAssociation, _res(f"patient-doctor-link/{link_id}")) in g
    assert (_res(f"investigation/{inv_id}/v1"), PROV.wasGeneratedBy, _activity(opened)) in g
    assert (_activity(opened), PROV.wasAssociatedWith, patient_agent) in g

    # Messages: entities attributed to their author, linked to the investigation, no content.
    message_events = world.events("InvestigationMessageAdded", inv_id)
    assert len(message_events) == 3  # initial, reply, closing observation
    for event in message_events:
        message = _res(f"investigation-message/{event.metadata_json['message_id']}")
        assert (message, RDF.type, MYGV.InvestigationMessage) in g
        assert (message, PROV.wasGeneratedBy, _activity(event)) in g
        assert (message, MYGV.partOfInvestigation, inv) in g
        assert set(g.predicates(message)) <= {RDF.type, PROV.wasGeneratedBy, PROV.wasAttributedTo,
                                               MYGV.partOfInvestigation, MYGV.messageSequence}
    reply_event = next(e for e in message_events if e.metadata_json.get("author_role") == "DOCTOR")
    reply = _res(f"investigation-message/{reply_event.metadata_json['message_id']}")
    assert (reply, PROV.wasAttributedTo, doctor_agent) in g
    assert (_res(f"investigation/{inv_id}/v2"), PROV.wasRevisionOf, _res(f"investigation/{inv_id}/v1")) in g
    initial = next(e for e in message_events if e.metadata_json.get("sequence") == 1)
    assert (_activity(initial), PROV.wasInformedBy, _activity(opened)) in g

    # Participant closing and automatic closure caused by the revocation.
    (closed,) = world.events("InvestigationClosed", inv_id)
    assert (_res(f"investigation/{inv_id}/v3"), PROV.wasGeneratedBy, _activity(closed)) in g
    (auto,) = world.events("InvestigationClosedByAssociationRevocation", scenario["still_open"]["id"])
    assert (_activity(auto), PROV.wasAssociatedWith, collaboration) in g
    assert (_activity(auto), PROV.wasInformedBy, _activity(revoke)) in g

    # Read marker, notification and access events.
    (read,) = world.events("InvestigationReadAdvanced", inv_id)
    assert (_res(f"investigation/{inv_id}/read-position/patient/2"), PROV.wasGeneratedBy, _activity(read)) in g
    (note_read,) = world.events("NotificationRead", scenario["note"]["id"])
    assert (_activity(note_read), PROV.used, _res(f"notification/{scenario['note']['id']}")) in g
    created = [e for e in world.events("NotificationCreated", scenario["note"]["id"])]
    assert created and (_activity(created[0]), PROV.wasAssociatedWith, collaboration) in g
    for event in world.events("PatientDetailFilterApplied", patient.id):
        assert (_activity(event), PROV.used, _res(f"patient/{patient.id}")) in g


def test_projection_includes_software_prompt_creation(world: World):
    patient, prompts = world.atypical_patient()
    _json, _ttl, g = _project(patient.id)
    prompt_events = [e for e in world.events("AtypicalDayInvestigationPromptCreated")
                     if (e.metadata_json or {}).get("patient_id") == patient.id]
    assert prompt_events
    for event in prompt_events:
        assert (_activity(event), PROV.wasAssociatedWith, EX["myglico-analytics"]) in g
        prompt = _res(f"atypical-day-prompt/{event.entity_id}")
        indicator = _res(f"daily-indicator/{event.metadata_json['daily_indicator_id']}")
        assert (prompt, PROV.wasGeneratedBy, _activity(event)) in g
        assert (prompt, MYGV.promptsForAtypicalDay, indicator) in g
    assert (EX["myglico-analytics"], RDF.type, PROV.SoftwareAgent) in g


def test_projection_ids_are_stable_and_scope_is_per_patient(scenario: dict, world: World):
    patient = scenario["patient"]
    first_json, first_ttl, first = _project(patient.id)
    second_json, second_ttl, second = _project(patient.id)
    assert isomorphic(first, second)
    subjects = {s for s in first.subjects() if isinstance(s, URIRef)}
    assert subjects == {s for s in second.subjects() if isinstance(s, URIRef)}

    other, _prompts = world.atypical_patient()
    _o_json, _o_ttl, other_graph = _project(other.id)
    other_subjects = {s for s in other_graph.subjects() if isinstance(s, URIRef)}
    assert not any(str(s).endswith(scenario["link"]["id"]) for s in other_subjects)
    assert _res(f"investigation/{scenario['investigation']['id']}") not in other_subjects


def test_serialized_projection_has_no_message_content_or_pii(scenario: dict):
    json_text, turtle, graph = _project(scenario["patient"].id)
    for secret in scenario["secrets"]:
        assert secret and secret not in json_text, secret
        assert secret not in turtle, secret
    literals = {str(o) for o in graph.objects() if isinstance(o, Literal)}
    assert literals, "projection unexpectedly has no literals"
    assert not any(secret in literal for literal in literals for secret in scenario["secrets"])


def test_cli_refuses_public_destinations(tmp_path: Path):
    cli = _load_cli()
    for public in (REPO_ROOT / "artifacts", REPO_ROOT / "artifacts" / "cscw-audit",
                   REPO_ROOT / "frontend-react" / "dist" / "x"):
        with pytest.raises(cli.UnsafeOutputDir):
            cli.validate_output_dir(public)
    target = REPO_ROOT / "artifacts" / f"cscw-refused-{uuid.uuid4().hex[:8]}"
    result = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "export_cscw_provenance.py"),
                             "--output", str(target)], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 2, result.stderr
    assert "publicly served" in result.stderr
    assert not target.exists()
    missing = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "export_cscw_provenance.py")],
                             capture_output=True, text=True, cwd=REPO_ROOT)
    assert missing.returncode != 0 and "--output" in missing.stderr


def test_cli_exports_parseable_json_and_turtle(scenario: dict, tmp_path: Path):
    import json

    cli = _load_cli()
    json_path, ttl_path = cli.export(tmp_path / "audit", patient_id=scenario["patient"].id)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["activity"] and data["agent"] and data["entity"]
    graph = Graph()
    graph.parse(ttl_path, format="turtle")
    assert len(graph) > 0
    text = json_path.read_text(encoding="utf-8") + ttl_path.read_text(encoding="utf-8")
    for secret in scenario["secrets"]:
        assert secret not in text
