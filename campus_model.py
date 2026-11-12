
import sqlite3

MATRIX = {
    ("High", "High"): "M1",
    ("High", "Medium"): "M2",
    ("High", "Low"): "M3",
    ("Medium", "High"): "M2",
    ("Medium", "Medium"): "M3",
    ("Medium", "Low"): "M4",
    ("Low", "High"): "M3",
    ("Low", "Medium"): "M4",
    ("Low", "Low"): "M4"
}

KEYWORDS = {
    "Facilities": ["leak", "flood", "ceiling", "door", "lock"],
    "HVAC": ["ac", "compressor", "temperature", "cooling"],
    "AV-Network": ["projector", "display", "wifi", "network"]
}

MAX_MINUTES = 180
TEMP_LIMIT = 28.0

TRANSITIONS = {
    "New": ["Assigned"],
    "Assigned": ["In Progress"],
    "In Progress": ["Resolved"],
    "Resolved": ["Closed"],
    "Closed": []
}

APPROVERS = {"approver", "manager"}


def priority(impact, urgency):
    if (impact, urgency) not in MATRIX:
        raise ValueError("Invalid priority input")
    return MATRIX[(impact, urgency)]


def classify(text):
    words = text.lower().replace(",", " ").split()
    scores = {
        category: sum(1 for word in words if word in keywords)
        for category, keywords in KEYWORDS.items()
    }

    best = max(scores.values())
    top = [c for c, score in scores.items() if score == best]

    if best == 0 or len(top) != 1:
        return "Manual Review"

    return top[0]


def breached(value):
    return value > TEMP_LIMIT


def valid_duration(minutes):
    return 0 < minutes <= MAX_MINUTES


def overlaps(s1, e1, s2, e2):
    return s1 < e2 and s2 < e1


class Store:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)

        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS tickets(
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            state TEXT NOT NULL,
            version INTEGER NOT NULL,
            notes TEXT,
            source TEXT,
            event_id TEXT,
            UNIQUE(source, event_id)
        );

        CREATE TABLE IF NOT EXISTS audit(
            id INTEGER PRIMARY KEY,
            ticket_id INTEGER,
            from_state TEXT,
            to_state TEXT,
            actor TEXT
        );

        CREATE TABLE IF NOT EXISTS bookings(
            id INTEGER PRIMARY KEY,
            facility TEXT,
            start_min INTEGER,
            end_min INTEGER,
            status TEXT
        );
        """)

        self.db.commit()

    def create_ticket(self, title, source=None, event_id=None):
        if not title or not title.strip():
            raise ValueError("Title required")

        if source is not None:
            row = self.db.execute(
                "SELECT id FROM tickets WHERE source=? AND event_id=?",
                (source, event_id)
            ).fetchone()

            if row:
                return row[0]

        cur = self.db.execute(
            """INSERT INTO tickets
            (title, state, version, source, event_id)
            VALUES (?, ?, ?, ?, ?)""",
            (title, "New", 1, source, event_id)
        )

        self.db.commit()
        return cur.lastrowid

    def count(self, table="tickets"):
        if table not in {"tickets", "bookings", "audit"}:
            raise ValueError("Invalid table")

        return self.db.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

    def state(self, tid):
        return self.db.execute(
            "SELECT state, version FROM tickets WHERE id=?",
            (tid,)
        ).fetchone()

    def transition(self, tid, target, expected_version, role, notes=None):
        if role not in {"technician", "manager"}:
            raise PermissionError("Role not permitted")

        current = self.state(tid)

        if current is None:
            raise ValueError("Ticket not found")

        state, version = current

        if target not in TRANSITIONS[state]:
            raise ValueError("Invalid transition")

        if target == "Resolved" and not (notes and notes.strip()):
            raise ValueError("Resolution notes required")

        cur = self.db.execute(
            """UPDATE tickets
            SET state=?, version=version+1,
                notes=COALESCE(?, notes)
            WHERE id=? AND version=?""",
            (target, notes, tid, expected_version)
        )

        if cur.rowcount != 1:
            self.db.rollback()
            raise RuntimeError("Stale version")

        self.db.execute(
            """INSERT INTO audit
            (ticket_id, from_state, to_state, actor)
            VALUES (?, ?, ?, ?)""",
            (tid, state, target, role)
        )

        self.db.commit()
        return version + 1

    def audit_count(self, tid):
        return self.db.execute(
            "SELECT COUNT(*) FROM audit WHERE ticket_id=?",
            (tid,)
        ).fetchone()[0]

    def request_booking(self, facility, start, end):
        if not valid_duration(end - start):
            raise ValueError("Duration outside policy")

        rows = self.db.execute(
            """SELECT start_min, end_min
            FROM bookings
            WHERE facility=? AND status='Pending'""",
            (facility,)
        ).fetchall()

        for s, e in rows:
            if overlaps(start, end, s, e):
                raise RuntimeError("Booking overlap")

        cur = self.db.execute(
            """INSERT INTO bookings
            (facility, start_min, end_min, status)
            VALUES (?, ?, ?, 'Pending')""",
            (facility, start, end)
        )

        self.db.commit()
        return cur.lastrowid

    def approve_booking(self, bid, role):
        if role not in APPROVERS:
            raise PermissionError("Role not permitted")

        cur = self.db.execute(
            """UPDATE bookings SET status='Approved'
            WHERE id=? AND status='Pending'""",
            (bid,)
        )

        if cur.rowcount != 1:
            self.db.rollback()
            raise ValueError("Booking not pending or not found")

        self.db.commit()

    def booking_status(self, bid):
        row = self.db.execute(
            "SELECT status FROM bookings WHERE id=?",
            (bid,)
        ).fetchone()

        return row[0] if row else None
