"""Doctor home: the original patient list, scoped to the doctor's ACTIVE links."""
from __future__ import annotations

from conftest import World


def _listed_ids(actor) -> set[str]:
    response = actor.client.get("/api/patients", params={"page_size": 50})
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["patients"]}


def test_doctor_lists_only_active_linked_patients(world: World):
    doctor, other_doctor = world.doctor(), world.doctor()
    active, pending, revoked, foreign = (world.patient() for _ in range(4))
    world.active_link(active, doctor)
    world.request_link(pending, doctor)
    link = world.active_link(revoked, doctor)
    revoke = revoked.client.post(f"/api/doctor-links/{link['id']}/revoke", json={"version": link["version"]})
    assert revoke.status_code == 200, revoke.text
    world.active_link(foreign, other_doctor)

    assert _listed_ids(doctor) == {active.id}
    assert _listed_ids(other_doctor) == {foreign.id}

    dashboard = doctor.client.get("/api/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["metrics"]["patient_count"] == 1


def test_patient_still_lists_only_itself_and_doctor_without_links_lists_nothing(world: World):
    patient, lonely_doctor = world.patient(), world.doctor()
    assert _listed_ids(patient) == {patient.id}
    assert _listed_ids(lonely_doctor) == set()
    assert lonely_doctor.client.get("/api/dashboard").json()["metrics"]["patient_count"] == 0
