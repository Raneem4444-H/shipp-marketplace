"""Exercises LakebaseRepo's real SQL flow against a fake psycopg connection.

The fake mimics psycopg 3 semantics that save_item depends on: the connection
context manager commits on clean exit and discards writes on exception.
"""

from datetime import timedelta

from agent_fakes import NOW
from shipp.agent.contracts import ActionStatus
from shipp.agent.lakebase import LakebaseRepo


class FakeDB:
    def __init__(self):
        self.requests = {"req-1": ("req-1", "user-1", "open")}
        self.listings = {"l1": ("l1", "available", NOW + timedelta(days=5))}
        self.saved = {}
        self.activity = []
        self.fail_on_insert_saved = False
        self.statements = []


class FakeCursor:
    def __init__(self, db, staged):
        self.db, self.staged, self._result = db, staged, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        self.db.statements.append(sql)
        if "FROM bootcamp_shipp.requests" in sql:
            self._result = self.db.requests.get(params[0])
        elif "FROM bootcamp_shipp.listings" in sql:
            self._result = self.db.listings.get(params[0])
        elif "INSERT INTO bootcamp_shipp.saved_items" in sql:
            if self.db.fail_on_insert_saved:
                raise RuntimeError("connection reset")
            saved_id, user, req, lst, _ = params
            key = (user, req, lst)
            if key in self.db.saved or key in self.staged["saved"]:
                self._result = None
            else:
                self.staged["saved"][key] = saved_id
                self._result = (saved_id,)
        elif "INSERT INTO bootcamp_shipp.agent_activity" in sql:
            self.staged["activity"].append((params[2], params[3], params[4]))
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._result


class FakeConn:
    def __init__(self, db):
        self.db = db
        self.staged = {"saved": {}, "activity": []}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *rest):
        if exc_type is None:  # commit
            self.db.saved.update(self.staged["saved"])
            self.db.activity.extend(self.staged["activity"])
        return False  # rollback = drop staged, re-raise

    def cursor(self):
        return FakeCursor(self.db, self.staged)


def repo(db):
    return LakebaseRepo(lambda: FakeConn(db), "bootcamp_shipp")


def test_successful_save_writes_item_and_activity_together():
    db = FakeDB()
    result = repo(db).save_item(user_id="user-1", request_id="req-1", listing_id="l1", now=NOW)
    assert result.ok and result.saved_item_id
    assert len(db.saved) == 1
    assert db.activity == [("save_item", "l1", "SUCCESS")]
    assert any("FOR SHARE" in s for s in db.statements)


def test_second_save_is_duplicate_not_error():
    db = FakeDB()
    r = repo(db)
    r.save_item(user_id="user-1", request_id="req-1", listing_id="l1", now=NOW)
    result = r.save_item(user_id="user-1", request_id="req-1", listing_id="l1", now=NOW)
    assert result.status is ActionStatus.REJECTED_DUPLICATE
    assert len(db.saved) == 1


def test_withdrawn_listing_rejected_and_audited():
    db = FakeDB()
    db.listings["l1"] = ("l1", "withdrawn", None)
    result = repo(db).save_item(user_id="user-1", request_id="req-1", listing_id="l1", now=NOW)
    assert result.status is ActionStatus.REJECTED
    assert db.saved == {}
    assert db.activity == [("save_item", "l1", "rejected")]


def test_wrong_owner_never_reads_listing():
    db = FakeDB()
    result = repo(db).save_item(user_id="intruder", request_id="req-1", listing_id="l1", now=NOW)
    assert result.status is ActionStatus.REJECTED
    assert not any("FROM bootcamp_shipp.listings" in s for s in db.statements)


def test_db_error_rolls_back_and_logs_failure_separately():
    db = FakeDB()
    db.fail_on_insert_saved = True
    result = repo(db).save_item(user_id="user-1", request_id="req-1", listing_id="l1", now=NOW)
    assert result.status is ActionStatus.FAILED
    assert db.saved == {}
    assert db.activity == [("save_item", "l1", "failed")]
