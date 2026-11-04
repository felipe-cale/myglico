from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import encrypt_field
from app.db.base import Base
from app.models.entities import Doctor, Patient, PatientDoctorLink, UserAccount
from app.services.auth_service import doctor_payload
from app.services.doctor_links import list_links


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("MYGLICO_ENCRYPTION_KEY_V1", "1" * 64)
    monkeypatch.setenv("MYGLICO_LOOKUP_HMAC_KEY", "2" * 64)
    get_settings.cache_clear()
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()
    get_settings.cache_clear()


def make_doctor(db, index):
    account = UserAccount(email=f"doctor{index}@demo.invalid", password_hash="unused", is_demo=True)
    db.add(account)
    db.flush()
    doctor_id = str(uuid4())
    doctor = Doctor(id=doctor_id, user_account=account, short_id=f"D{index:05}", is_demo=True,
        name_encrypted=encrypt_field(f"Doctor {index}", table="doctors", column="name", record_id=doctor_id))
    db.add(doctor)
    db.flush()
    return doctor


def make_patient(db, index):
    patient = Patient(name=f"Patient {index}", short_id=f"P{index:05}")
    db.add(patient)
    db.flush()
    return patient


@pytest.mark.parametrize("role", ["doctor", "patient"])
def test_page_relationships_are_loaded_without_per_link_queries(db, role):
    owner = make_doctor(db, 0) if role == "doctor" else make_patient(db, 0)
    owner_id = owner.id
    for index in range(1, 61):
        counterpart = make_patient(db, index) if role == "doctor" else make_doctor(db, index)
        db.add(PatientDoctorLink(
            doctor=owner if role == "doctor" else counterpart,
            patient=counterpart if role == "doctor" else owner,
            status="ACTIVE"))
    stranger_doctor = make_doctor(db, 99)
    stranger_patient = make_patient(db, 99)
    db.add(PatientDoctorLink(doctor=stranger_doctor, patient=stranger_patient, status="ACTIVE"))
    db.commit()
    stranger_id = stranger_patient.id
    db.expunge_all()
    principal = SimpleNamespace(
        doctor=db.get(Doctor, owner_id) if role == "doctor" else None,
        patient=db.get(Patient, owner_id) if role == "patient" else None)
    statements = []

    def record(*args):
        statements.append(args[2])

    event.listen(db.bind, "before_cursor_execute", record)
    try:
        links, total, page = list_links(db, principal, status="active", page_size=50)
        # Serialize the identities read by the API for each returned association.
        payload = [(doctor_payload(link.doctor), link.patient.display_name) for link in links]
    finally:
        event.remove(db.bind, "before_cursor_execute", record)
    assert total == 60 and page == 1 and len(payload) == 50
    assert len(statements) == 2
    second, total, page = list_links(db, principal, status="active", page=2, page_size=50)
    assert page == 2 and total == 60 and len(second) == 10
    assert {link.id for link in links}.isdisjoint(link.id for link in second)
    assert list_links(db, principal, patient_id=stranger_id)[0] == []
    target, _, target_page = list_links(db, principal, page_size=10, link_id=second[-1].id)
    assert target_page == 6 and second[-1].id in {link.id for link in target}
