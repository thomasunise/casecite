"""HTTP-level tests for the jobs router (/api/v1/jobs).

Cross-user access is covered in test_tenant_isolation.py; these cover
authentication, the happy paths and request bounds.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from app.services.job_queue import job_manager

from tests.helpers import headers, make_user

pytestmark = pytest.mark.usefixtures("no_rate_limit")

BASE = "/api/v1/jobs"


def _job(owner, status="processing") -> dict:
    return {
        "job_id": f"job-{uuid.uuid4().hex}",
        "user_id": owner.id,
        "endpoint": "/contract-analysis/compare",
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
    }


@pytest.mark.parametrize(("method", "path"), [("get", ""), ("get", "/abc"), ("delete", "/abc")])
def test_requires_authentication(client, method, path):
    assert getattr(client, method)(f"{BASE}{path}").status_code == 401


def test_poll_own_job(client):
    owner = make_user("job-owner")
    job = _job(owner, status="completed") | {"result": {"answer": 42}}
    with patch.object(job_manager, "_load_job", return_value=job):
        resp = client.get(f"{BASE}/{job['job_id']}", headers=headers(owner))
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    assert resp.json()["result"] == {"answer": 42}


def test_unknown_job_is_404(client):
    owner = make_user("job-owner")
    with patch.object(job_manager, "_load_job", return_value=None):
        assert client.get(f"{BASE}/missing", headers=headers(owner)).status_code == 404


def test_list_returns_only_the_callers_jobs(client):
    owner, other = make_user("job-owner"), make_user("job-other")
    mine, theirs = _job(owner), _job(other)
    jobs = {mine["job_id"]: mine, theirs["job_id"]: theirs}
    with (
        patch.object(job_manager, "_load_job", side_effect=jobs.get),
        # Even if the index wrongly returned someone else's id, it must be filtered out.
        patch.object(job_manager, "_get_user_job_ids", return_value=list(jobs)),
    ):
        resp = client.get(BASE, headers=headers(owner))
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert [j["job_id"] for j in body["jobs"]] == [mine["job_id"]]


@pytest.mark.parametrize("limit", [0, 101])
def test_list_limit_is_bounded(client, limit):
    owner = make_user("job-owner")
    assert client.get(f"{BASE}?limit={limit}", headers=headers(owner)).status_code == 422


def test_cancel_own_job(client):
    owner = make_user("job-owner")
    with patch.object(job_manager, "cancel_job", AsyncMock(return_value=True)) as cancel:
        resp = client.delete(f"{BASE}/job-1", headers=headers(owner))
    assert resp.status_code == 200
    assert resp.json() == {"status": "cancelled", "job_id": "job-1"}
    cancel.assert_awaited_once_with("job-1", owner.id)


def test_cancel_finished_job_is_404(client):
    owner = make_user("job-owner")
    job = _job(owner, status="completed")
    with patch.object(job_manager, "_load_job", return_value=job):
        resp = client.delete(f"{BASE}/{job['job_id']}", headers=headers(owner))
    assert resp.status_code == 404
