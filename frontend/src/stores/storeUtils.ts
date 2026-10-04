import { useUIStore } from './uiStore';

/** Show a toast from store code (outside React). */
export function toast(msg: string, type = 'info'): void {
  try { useUIStore.getState().addToast(msg, type); } catch { /* noop */ }
}

interface PollableJob {
  status: string; // pending | processing | completed | failed | cancelled
  error?: string | null;
}

export interface JobPollOptions<J extends PollableJob> {
  fetchJob: () => Promise<J>;
  /** The job reached `completed`. */
  onCompleted: (job: J) => void;
  /** The job failed or was cancelled, the wait budget ran out, or polling itself threw. */
  onFailed: (message: string) => void;
  /** Called on every poll that finds the job still running. */
  onPending?: (job: J, attempt: number) => void;
  /** Give up after this many polls. */
  maxAttempts: number;
  intervalMs?: number;
  failedMessage: string;
  timeoutMessage: string;
}

const DEFAULT_POLL_INTERVAL_MS = 2000;

/**
 * Poll a background job until it settles. One poller runs at most one poll
 * loop: `start` supersedes any earlier loop and `stop` cancels it, including
 * a status request that is already in flight — its answer is discarded, so a
 * stopped (or reset) store is never written to by a stale job.
 */
export function createJobPoller() {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let generation = 0;

  const stop = () => {
    generation += 1;
    if (timer) { clearTimeout(timer); timer = null; }
  };

  const start = <J extends PollableJob>(opts: JobPollOptions<J>) => {
    stop();
    const mine = generation;
    const poll = async (attempt: number) => {
      try {
        const job = await opts.fetchJob();
        if (mine !== generation) return;
        if (job.status === 'completed') { opts.onCompleted(job); return; }
        if (job.status === 'failed' || job.status === 'cancelled') {
          opts.onFailed(job.error || opts.failedMessage);
          return;
        }
        if (attempt > opts.maxAttempts) { opts.onFailed(opts.timeoutMessage); return; }
        opts.onPending?.(job, attempt);
        timer = setTimeout(() => poll(attempt + 1), opts.intervalMs ?? DEFAULT_POLL_INTERVAL_MS);
      } catch (e) {
        if (mine !== generation) return;
        opts.onFailed(e instanceof Error ? e.message : 'Polling failed.');
      }
    };
    poll(0);
  };

  return { start, stop };
}
