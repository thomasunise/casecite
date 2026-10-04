import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createJobPoller } from './storeUtils';

type Job = { status: string; error?: string | null; result?: string };

function options(fetchJob: () => Promise<Job>) {
  return {
    fetchJob,
    maxAttempts: 3,
    intervalMs: 1000,
    failedMessage: 'Job failed.',
    timeoutMessage: 'Timed out.',
    onCompleted: vi.fn(),
    onFailed: vi.fn(),
    onPending: vi.fn(),
  };
}

describe('createJobPoller', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('polls until the job completes', async () => {
    const fetchJob = vi.fn<() => Promise<Job>>()
      .mockResolvedValueOnce({ status: 'processing' })
      .mockResolvedValueOnce({ status: 'completed', result: 'done' });
    const opts = options(fetchJob);

    createJobPoller().start(opts);
    await vi.advanceTimersByTimeAsync(0);
    expect(opts.onPending).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);

    expect(opts.onCompleted).toHaveBeenCalledWith({ status: 'completed', result: 'done' });
    expect(opts.onFailed).not.toHaveBeenCalled();
  });

  it('reports a failed job with the server message, or the fallback', async () => {
    const withMessage = options(vi.fn().mockResolvedValue({ status: 'failed', error: 'Out of quota' }));
    createJobPoller().start(withMessage);
    await vi.advanceTimersByTimeAsync(0);
    expect(withMessage.onFailed).toHaveBeenCalledWith('Out of quota');

    const cancelled = options(vi.fn().mockResolvedValue({ status: 'cancelled' }));
    createJobPoller().start(cancelled);
    await vi.advanceTimersByTimeAsync(0);
    expect(cancelled.onFailed).toHaveBeenCalledWith('Job failed.');
  });

  it('gives up after the attempt budget', async () => {
    const opts = options(vi.fn().mockResolvedValue({ status: 'processing' }));
    createJobPoller().start(opts);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(opts.onFailed).toHaveBeenCalledWith('Timed out.');
    expect(opts.onCompleted).not.toHaveBeenCalled();
  });

  it('reports a polling error', async () => {
    const opts = options(vi.fn().mockRejectedValue(new Error('Network down')));
    createJobPoller().start(opts);
    await vi.advanceTimersByTimeAsync(0);
    expect(opts.onFailed).toHaveBeenCalledWith('Network down');
  });

  it('stop() discards the answer of a status request already in flight', async () => {
    let resolve!: (job: Job) => void;
    const opts = options(vi.fn(() => new Promise<Job>((r) => { resolve = r; })));
    const poller = createJobPoller();
    poller.start(opts);

    poller.stop();
    resolve({ status: 'completed', result: 'stale' });
    await vi.advanceTimersByTimeAsync(5000);

    expect(opts.onCompleted).not.toHaveBeenCalled();
    expect(opts.onFailed).not.toHaveBeenCalled();
  });
});
