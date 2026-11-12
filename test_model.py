
import pytest
import campus_model as m


# UNIT TESTS

def test_U1_high_high():
    assert m.priority("High", "High") == "M1"


def test_U2_low_low():
    assert m.priority("Low", "Low") == "M4"


def test_U3_invalid_priority():
    with pytest.raises(ValueError):
        m.priority("Critical", "High")


def test_U4_water_leak():
    assert m.classify("Water leak from lab ceiling") == "Facilities"


def test_U5_equal_evidence():
    assert m.classify("leak and projector fault") == "Manual Review"


def test_U6_temperature_threshold():
    assert (m.breached(28.00), m.breached(28.01)) == (False, True)


# INTEGRATION TESTS

def test_I1_ticket_persistence(tmp_path):
    path = str(tmp_path / "campus.db")
    s = m.Store(path)

    tid = s.create_ticket("AC compressor problem")

    for target, notes in [
        ("Assigned", None),
        ("In Progress", None),
        ("Resolved", "Reset breaker"),
        ("Closed", None)
    ]:
        current_version = s.state(tid)[1]
        s.transition(tid, target, current_version, "technician", notes)

    s.db.close()

    s2 = m.Store(path)

    assert s2.state(tid) == ("Closed", 5)
    assert s2.audit_count(tid) == 4


def test_I2_duplicate_sensor_event():
    s = m.Store()

    ids = [
        s.create_ticket("Temperature alert", "sensor-7", "event-1")
        for _ in range(5)
    ]

    assert len(set(ids)) == 1
    assert s.count("tickets") == 1


def test_I3_student_cannot_approve():
    s = m.Store()
    bid = s.request_booking("Lab-204", 600, 720)

    with pytest.raises(PermissionError):
        s.approve_booking(bid, "student")

    assert s.booking_status(bid) == "Pending"


def test_I4_booking_overlap():
    s = m.Store()

    s.request_booking("Lab-204", 600, 720)

    with pytest.raises(RuntimeError):
        s.request_booking("Lab-204", 700, 800)

    s.request_booking("Lab-204", 720, 840)

    assert s.count("bookings") == 2


# REGRESSION TESTS

def test_R1_high_medium_priority():
    assert m.priority("High", "Medium") == "M2"


def test_R2_unknown_category():
    assert m.classify("Strange noise somewhere") == "Manual Review"


def test_R3_resolution_requires_notes():
    s = m.Store()
    tid = s.create_ticket("Door lock problem")

    s.transition(tid, "Assigned", 1, "technician")
    s.transition(tid, "In Progress", 2, "technician")

    with pytest.raises(ValueError):
        s.transition(tid, "Resolved", 3, "technician", "")


def test_R4_invalid_transition():
    s = m.Store()
    tid = s.create_ticket("Display problem")

    with pytest.raises(ValueError):
        s.transition(tid, "Closed", 1, "technician")

    assert s.state(tid) == ("New", 1)
