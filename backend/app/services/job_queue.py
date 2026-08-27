"""
Persistent Async Job Queue for AI/Document Workloads

Provides a unified job queue backed by Redis (with in-memory fallback)
for long-running AI and document processing tasks. Jobs run in-process
via asyncio.create_task() — no external worker needed.

Features:
- Redis-backed state persistence with configurable TTLs
- Per-endpoint retry policies with exponential backoff
- Dead-letter queue for permanently failed jobs
- Graceful shutdown with task draining
- Orphan recovery on startup
- User-scoped job access control
"""

import asyncio
import contextvars
import json
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from app.config import settings
from app.redis_utils import RedisError, get_redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RESULT_TTL = getattr(settings, "job_result_ttl", 1800)  # 30 min
_FAILED_TTL = getattr(settings, "job_failed_ttl", 86400)  # 24 h
_DEAD_LETTER_TTL = getattr(settings, "job_dead_letter_ttl", 604800)  # 7 d
_MAX_RESULT_SIZE = getattr(settings, "job_max_result_size", 1_048_576)  # 1 MB
_SHUTDOWN_TIMEOUT = getattr(settings, "job_shutdown_timeout", 30)
_PROCESSING_TTL = 7200  # 2 h — pending/processing jobs

# The job a coroutine is running under, so work deep inside a pipeline can
# report progress without threading the job id through every signature.
_current_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "job_queue_current_job_id", default=None
)


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Retry policies
# ---------------------------------------------------------------------------


@dataclass
class RetryPolicy:
    """Configurable retry behaviour per endpoint category."""

    max_retries: int = 2
    backoff_base: float = 3.0
    max_delay: float = 30.0
    retryable_exceptions: tuple = (
        ConnectionError,
        TimeoutError,
        OSError,
        RuntimeError,
    )


# Pre-built policies referenced by routers
RETRY_POLICIES: dict[str, RetryPolicy] = {
    "ai_analysis": RetryPolicy(max_retries=2, backoff_base=3.0, max_delay=30.0),
    "external_api": RetryPolicy(max_retries=3, backoff_base=2.0, max_delay=20.0),
    "cpu_bound": RetryPolicy(max_retries=1, backoff_base=1.0, max_delay=5.0),
}


# ---------------------------------------------------------------------------
# JobManager
# ---------------------------------------------------------------------------


class JobManager:
    """In-process async job queue with Redis persistence."""

    def __init__(self) -> None:
        # Active asyncio.Task objects keyed by job_id (for cancellation)
        self._tasks: dict[str, asyncio.Task] = {}
        # In-memory fallback when Redis is unavailable
        self._memory: dict[str, dict] = {}
        # Bound concurrent execution so a burst of submissions can't exhaust
        # memory / DB / upstream connections in the API process.
        self._semaphore = asyncio.Semaphore(getattr(settings, "job_max_concurrency", 5))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit(
        self,
        coro_factory: Callable[..., Coroutine],
        *,
        user_id: str,
        endpoint: str,
        retry_policy: RetryPolicy | None = None,
    ) -> str:
        """Submit a coroutine factory for background execution.

        ``coro_factory`` is a zero-arg async callable that performs the work.

        Returns the ``job_id``.
        """
        job_id = str(uuid.uuid4())
        policy = retry_policy or RETRY_POLICIES.get("ai_analysis", RetryPolicy())

        now = datetime.now(UTC).isoformat()
        job_data = {
            "job_id": job_id,
            "user_id": user_id,
            "endpoint": endpoint,
            "status": JobStatus.PENDING.value,
            "created_at": now,
            "updated_at": now,
            "attempts": 0,
            "max_retries": policy.max_retries,
            "result": None,
            "error": None,
            "truncated": False,
            "progress": None,
        }

        self._save_job(job_id, job_data, ttl=_PROCESSING_TTL)
        self._add_user_job(user_id, job_id)

        task = asyncio.create_task(self._execute_job(job_id, coro_factory, policy))
        self._tasks[job_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(job_id, None))

        logger.info("Job %s submitted for %s (user=%s)", job_id, endpoint, user_id)
        return job_id

    def report_progress(
        self, message: str, fraction: float | None = None, job_id: str | None = None
    ) -> None:
        """Record progress on a running job. Best-effort; never raises.

        Called from inside the job's coroutine (the current job id is
        task-local), or with an explicit ``job_id``. Polling clients read it
        from ``GET /jobs/{id}`` as ``progress: {message, fraction}``.
        """
        job_id = job_id or _current_job_id.get()
        if not job_id:
            return
        try:
            data = self._load_job(job_id)
            if data is None or data.get("status") != JobStatus.PROCESSING.value:
                return
            now = datetime.now(UTC).isoformat()
            data["progress"] = {
                "message": str(message)[:500],
                "fraction": None if fraction is None else max(0.0, min(1.0, float(fraction))),
                "updated_at": now,
            }
            data["updated_at"] = now
            self._save_job(job_id, data, ttl=_PROCESSING_TTL)
        except Exception:  # progress must never fail the job
            logger.debug("Progress update for job %s failed", job_id, exc_info=True)

    def get_job(self, job_id: str, user_id: str) -> dict | None:
        """Fetch job data with ownership check."""
        data = self._load_job(job_id)
        if data is None:
            return None
        if data.get("user_id") != user_id:
            return None
        return data

    async def cancel_job(self, job_id: str, user_id: str) -> bool:
        """Cancel a running/pending job."""
        data = self._load_job(job_id)
        if data is None or data.get("user_id") != user_id:
            return False

        if data["status"] not in (JobStatus.PENDING.value, JobStatus.PROCESSING.value):
            return False

        # Cancel the asyncio task if running
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()

        data["status"] = JobStatus.CANCELLED.value
        data["updated_at"] = datetime.now(UTC).isoformat()
        self._save_job(job_id, data, ttl=_FAILED_TTL)
        logger.info("Job %s cancelled by user %s", job_id, user_id)
        return True

    def list_user_jobs(self, user_id: str, limit: int = 20) -> list[dict]:
        """List recent jobs for a user (most recent first)."""
        job_ids = self._get_user_job_ids(user_id, limit)
        jobs = []
        for jid in job_ids:
            data = self._load_job(jid)
            if data and data.get("user_id") == user_id:
                jobs.append(
                    {
                        "job_id": data["job_id"],
                        "endpoint": data.get("endpoint"),
                        "status": data["status"],
                        "created_at": data["created_at"],
                        "updated_at": data.get("updated_at"),
                    }
                )
        return jobs

    async def recover_orphans(self) -> int:
        """Mark stale processing/pending jobs as failed on startup."""
        count = 0
        redis_client = self._get_redis()
        if redis_client:
            try:
                keys = await asyncio.to_thread(redis_client.keys, "job:*")
                for key in keys:
                    raw = await asyncio.to_thread(redis_client.get, key)
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if data.get("status") in (
                        JobStatus.PENDING.value,
                        JobStatus.PROCESSING.value,
                    ):
                        data["status"] = JobStatus.FAILED.value
                        data["error"] = "Server restarted — job orphaned"
                        data["updated_at"] = datetime.now(UTC).isoformat()
                        await asyncio.to_thread(
                            redis_client.setex,
                            key,
                            _FAILED_TTL,
                            json.dumps(data),
                        )
                        count += 1
            except (RedisError, ConnectionError, OSError) as exc:
                logger.warning("Redis error during orphan recovery: %s", exc)
        else:
            # In-memory fallback
            for jid, data in list(self._memory.items()):
                if data.get("status") in (
                    JobStatus.PENDING.value,
                    JobStatus.PROCESSING.value,
                ):
                    data["status"] = JobStatus.FAILED.value
                    data["error"] = "Server restarted — job orphaned"
                    data["updated_at"] = datetime.now(UTC).isoformat()
                    count += 1

        if count:
            logger.warning("Recovered %d orphaned jobs", count)
        return count

    async def graceful_shutdown(self, timeout: int | None = None) -> None:
        """Cancel all running tasks and wait for them to drain."""
        timeout = timeout or _SHUTDOWN_TIMEOUT
        tasks = list(self._tasks.values())
        if not tasks:
            return

        logger.info("Draining %d in-flight jobs (timeout=%ds)...", len(tasks), timeout)
        for task in tasks:
            task.cancel()

        done, pending = await asyncio.wait(tasks, timeout=timeout)
        if pending:
            logger.warning("%d jobs did not finish within shutdown timeout", len(pending))

    # ------------------------------------------------------------------
    # Internal: job execution with retries
    # ------------------------------------------------------------------

    async def _execute_job(
        self,
        job_id: str,
        coro_factory: Callable[..., Coroutine],
        policy: RetryPolicy,
    ) -> None:
        data = self._load_job(job_id)
        if data is None:
            return

        # This task IS the job: anything it awaits can report progress.
        _current_job_id.set(job_id)

        # Wait for a free execution slot. Excess jobs stay PENDING (not running)
        # until a slot frees, bounding peak concurrency.
        await self._semaphore.acquire()
        try:
            await self._run_job_attempts(job_id, coro_factory, policy, data)
        finally:
            self._semaphore.release()

    async def _run_job_attempts(
        self,
        job_id: str,
        coro_factory: Callable[..., Coroutine],
        policy: RetryPolicy,
        data: dict,
    ) -> None:
        data["status"] = JobStatus.PROCESSING.value
        data["updated_at"] = datetime.now(UTC).isoformat()
        self._save_job(job_id, data, ttl=_PROCESSING_TTL)

        last_error: Exception | None = None
        for attempt in range(1, policy.max_retries + 2):  # +2 because first attempt isn't a "retry"
            data["attempts"] = attempt
            try:
                result = await coro_factory()
                # Serialise result
                result_json = json.dumps(result, default=str)
                truncated = False
                if len(result_json) > _MAX_RESULT_SIZE:
                    result_json = json.dumps(
                        {"_truncated": True, "message": "Result exceeded 1 MB limit"},
                        default=str,
                    )
                    truncated = True

                data["status"] = JobStatus.COMPLETED.value
                data["result"] = json.loads(result_json)
                data["truncated"] = truncated
                data["error"] = None
                data["updated_at"] = datetime.now(UTC).isoformat()
                self._save_job(job_id, data, ttl=_RESULT_TTL)
                logger.info("Job %s completed (attempt %d)", job_id, attempt)
                return

            except asyncio.CancelledError:
                data["status"] = JobStatus.CANCELLED.value
                data["updated_at"] = datetime.now(UTC).isoformat()
                self._save_job(job_id, data, ttl=_FAILED_TTL)
                logger.info("Job %s cancelled during execution", job_id)
                return

            except Exception as exc:
                last_error = exc
                is_retryable = isinstance(exc, policy.retryable_exceptions)
                is_last_attempt = attempt >= policy.max_retries + 1

                if is_retryable and not is_last_attempt:
                    delay = min(policy.backoff_base**attempt, policy.max_delay)
                    logger.warning(
                        "Job %s attempt %d failed (%s), retrying in %.1fs",
                        job_id,
                        attempt,
                        exc,
                        delay,
                    )
                    data["error"] = f"Attempt {attempt}: {exc}"
                    data["updated_at"] = datetime.now(UTC).isoformat()
                    self._save_job(job_id, data, ttl=_PROCESSING_TTL)
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        data["status"] = JobStatus.CANCELLED.value
                        data["updated_at"] = datetime.now(UTC).isoformat()
                        self._save_job(job_id, data, ttl=_FAILED_TTL)
                        return
                else:
                    break

        # All retries exhausted — mark failed
        error_msg = str(last_error) if last_error else "Unknown error"
        data["status"] = JobStatus.FAILED.value
        data["error"] = error_msg
        data["updated_at"] = datetime.now(UTC).isoformat()
        self._save_job(job_id, data, ttl=_FAILED_TTL)

        # Dead-letter copy
        self._save_dead_letter(job_id, data)
        logger.error(
            "Job %s failed after %d attempts: %s",
            job_id,
            data["attempts"],
            error_msg,
        )

    # ------------------------------------------------------------------
    # Redis / memory helpers
    # ------------------------------------------------------------------

    def _get_redis(self):
        return get_redis()

    def _save_job(self, job_id: str, data: dict, ttl: int) -> None:
        redis_client = self._get_redis()
        if redis_client:
            try:
                redis_client.setex(f"job:{job_id}", ttl, json.dumps(data, default=str))
                return
            except (RedisError, ConnectionError, OSError):
                pass
        self._memory[job_id] = data

    def _load_job(self, job_id: str) -> dict | None:
        redis_client = self._get_redis()
        if redis_client:
            try:
                raw = redis_client.get(f"job:{job_id}")
                if raw:
                    return json.loads(raw)
            except (RedisError, ConnectionError, OSError):
                pass
        return self._memory.get(job_id)

    def _add_user_job(self, user_id: str, job_id: str) -> None:
        redis_client = self._get_redis()
        now = time.time()
        if redis_client:
            try:
                key = f"user_jobs:{user_id}"
                redis_client.zadd(key, {job_id: now})
                redis_client.expire(key, _FAILED_TTL)
                return
            except (RedisError, ConnectionError, OSError):
                pass
        # In-memory fallback — store in a simple list on the job itself
        # (user_jobs listing will scan _memory)

    def _get_user_job_ids(self, user_id: str, limit: int) -> list[str]:
        redis_client = self._get_redis()
        if redis_client:
            try:
                key = f"user_jobs:{user_id}"
                # Most recent first (highest score = newest)
                ids = redis_client.zrevrange(key, 0, limit - 1)
                return ids
            except (RedisError, ConnectionError, OSError):
                pass
        # In-memory fallback — scan all jobs
        user_jobs = [(jid, d) for jid, d in self._memory.items() if d.get("user_id") == user_id]
        user_jobs.sort(key=lambda x: x[1].get("created_at", ""), reverse=True)
        return [jid for jid, _ in user_jobs[:limit]]

    def _save_dead_letter(self, job_id: str, data: dict) -> None:
        redis_client = self._get_redis()
        if redis_client:
            try:
                redis_client.setex(
                    f"dead_letter:{job_id}",
                    _DEAD_LETTER_TTL,
                    json.dumps(data, default=str),
                )
            except (RedisError, ConnectionError, OSError):
                pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

job_manager = JobManager()
