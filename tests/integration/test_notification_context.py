"""Notifications name the counterpart for their recipient.

The listing enriches investigation_* and association_* items with the
counterpart's name, only while the recipient can still open that record.
Investigation titles never travel in notification payloads (CSCW-CA-31): the
client reads them from the investigation endpoints.
"""

from __future__ import annotations

from conftest import World


def _by_type(client, notification_type: str) -> list[dict]:
    response = client.get("/api/notifications", params={"page_size": 50})
    assert response.status_code == 200, response.text
    return [n for n in response.json()["notifications"] if n["notification_type"] == notification_type]


def test_investigation_notifications_name_the_conversation_and_sender(world: World):
    patient, doctor = world.patient(), world.doctor()
    world.active_link(patient, doctor)
    investigation = world.open_investigation(patient, doctor, title="Pico depois do almoço")
    reply = doctor.client.post(f"/api/investigations/{investigation['id']}/messages", json={"content": "Pode detalhar?"})
    assert reply.status_code == 201, reply.text

    opened = _by_type(doctor.client, "investigation_opened")
    assert len(opened) == 1
    assert opened[0]["context"] == {"counterpart_name": patient.display_name}
    assert opened[0]["payload"]["investigation_id"] == investigation["id"]

    added = _by_type(patient.client, "investigation_message_added")
    assert len(added) == 1
    assert added[0]["context"] == {"counterpart_name": doctor.display_name}

    for client in (doctor.client, patient.client):
        assert "Pico depois do almoço" not in client.get("/api/notifications", params={"page_size": 50}).text


def test_association_notifications_name_the_counterpart(world: World):
    patient, doctor = world.patient(), world.doctor()
    world.active_link(patient, doctor)

    requested = _by_type(doctor.client, "association_requested")
    assert len(requested) == 1
    assert requested[0]["context"] == {"counterpart_name": patient.display_name}

    confirmed = _by_type(patient.client, "association_confirmed")
    assert len(confirmed) == 1
    assert confirmed[0]["context"] == {"counterpart_name": doctor.display_name}


def test_revoked_doctor_no_longer_receives_the_counterpart_of_a_conversation(world: World):
    patient, doctor = world.patient(), world.doctor()
    link = world.active_link(patient, doctor)
    world.open_investigation(patient, doctor, title="Título reservado")
    assert _by_type(doctor.client, "investigation_opened")[0]["context"] == {"counterpart_name": patient.display_name}

    revoked = patient.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": link["version"]})
    assert revoked.status_code == 200, revoked.text

    listing = doctor.client.get("/api/notifications", params={"page_size": 50})
    assert listing.status_code == 200
    assert "Título reservado" not in listing.text
    for item in listing.json()["notifications"]:
        if item["notification_type"].startswith("investigation_"):
            assert item["context"] is None


def test_notification_context_never_crosses_accounts(world: World):
    patient, doctor, outsider = world.patient(), world.doctor(), world.doctor()
    world.active_link(patient, doctor)
    world.open_investigation(patient, doctor, title="Somente participantes")

    listing = outsider.client.get("/api/notifications", params={"page_size": 50})
    assert listing.status_code == 200
    assert "Somente participantes" not in listing.text
    assert patient.display_name not in listing.text
