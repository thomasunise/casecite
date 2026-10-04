"""
Job queue: bounded in-memory fallback and connector-sync retry policy.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

import asyncio
from unittest.mock import patch

import pytest
from app.services import job_queue
from app.services.job_queue import RETRY_POLICIES, JobManager, JobStatus, RetryPolicy


@pytest.fixture
def manager():
    """A JobManager with Redis unavailable, so the in-memory fallback is used."""
    with patch.object(JobManager, "_get_redis", return_value=None):
        yield JobManager()


def _job(status: str = JobStatus.COMPLETED.value, updated_at: str = "2026-01-01T00:00:00") -> dict:
    return {"job_id": "x", "user_id": "u1", "status": status, "updated_at": updated_at}


class TestMemoryFallbackIsBounded:
    def test_expired_jobs_are_evicted(self, manager):
        with patch.object(job_queue.time, "time", return_value=1000.0):
            manager._save_job("old", _job(), ttl=60)
        with patch.object(job_queue.time, "time", return_value=1061.0):
            assert manager._load_job("old") is None
            manager._save_job("new", _job(), ttl=60)
        assert set(manager._memory) == {"new"}
        assert set(manager._memory_expiry) == {"new"}

    def test_cap_drops_oldest_finished_jobs_first(self, manager):
        with patch.object(job_queue, "_MEMORY_MAX_JOBS", 3):
            manager._save_job("running", _job(JobStatus.PROCESSING.value, "2026-01-01"), ttl=600)
            manager._save_job("done-old", _job(updated_at="2026-01-02"), ttl=600)
            manager._save_job("done-new", _job(updated_at="2026-01-03"), ttl=600)
            manager._save_job("done-newest", _job(updated_at="2026-01-04"), ttl=600)
        # The running job is the oldest entry but is kept; the oldest finished goes.
        assert set(manager._memory) == {"running", "done-new", "done-newest"}

    def test_unexpired_job_is_still_readable(self, manager):
        manager._save_job("j", _job(), ttl=600)
        assert manager._load_job("j")["status"] == JobStatus.COMPLETED.value


class TestConnectorSyncRetries:
    @pytest.mark.asyncio
    async def test_sync_uses_the_modest_policy_whatever_the_caller_passes(self, manager):
        attempts = 0

        async def failing_sync():
            nonlocal attempts
            attempts += 1
            raise ConnectionError("provider unavailable")

        async def no_sleep(_delay):
            return None

        with patch.object(job_queue.asyncio, "sleep", no_sleep):
            job_id = await manager.submit(
                failing_sync,
                user_id="u1",
                endpoint="/connectors/google_drive/sync",
                retry_policy=RetryPolicy(max_retries=3),
            )
            await asyncio.wait_for(manager._tasks[job_id], timeout=5)

        # One retry, not the four attempts the "external_api" policy allowed.
        assert RETRY_POLICIES["connector_sync"].max_retries == 1
        assert attempts == 2
        assert manager.get_job(job_id, "u1")["status"] == JobStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_other_endpoints_keep_the_callers_policy(self, manager):
        attempts = 0

        async def flaky():
            nonlocal attempts
            attempts += 1
            raise TimeoutError("slow upstream")

        async def no_sleep(_delay):
            return None

        with patch.object(job_queue.asyncio, "sleep", no_sleep):
            job_id = await manager.submit(
                flaky,
                user_id="u1",
                endpoint="/judge-intel/build",
                retry_policy=RetryPolicy(max_retries=2),
            )
            await asyncio.wait_for(manager._tasks[job_id], timeout=5)

        assert attempts == 3
