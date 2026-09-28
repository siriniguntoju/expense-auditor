"""Optional real PostgreSQL integration, enabled by CI's isolated database."""

import os
from uuid import uuid4

import psycopg
import pytest

from auditor import study
from auditor.postgres import Connection
from auditor.store import Store


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="No isolated PostgreSQL test URL")
def test_postgres_review_and_study():
    url = os.environ["TEST_POSTGRES_URL"]
    schema = "test_" + uuid4().hex
    with psycopg.connect(url) as db:
        db.execute("CREATE SCHEMA " + schema)
    try:

        class TestStore(Store):
            def connect(self):
                c = Connection(self.path)
                c.execute("SET search_path TO " + schema)
                return c

        store = TestStore(url)
        store.start("run", "report-01")
        store.finish("run", {"flags": []})
        store.review("run", "approve", "Synthetic integration test")
        with pytest.raises(ValueError):
            store.review("run", "reject", "conflict")
        assert TestStore(url).get("run")["status"] == "approved"
        trial = study.start(store, "TEST_ONLY", "report-01", "manual", "fixture_replay")
        study.finish(store, trial["id"], "approve")
        assert study.summary(TestStore(url))["completed_trials"] == 1
    finally:
        with psycopg.connect(url) as db:
            db.execute("DROP SCHEMA " + schema + " CASCADE")
