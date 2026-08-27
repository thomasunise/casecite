import logger from '../utils/logger';

/**
 * Sign-out registry. Every store that holds a user's work product registers
 * a reset here (at module load — a store that was never loaded has nothing
 * to wipe). `resetAllStores()` runs on logout and on a dead, unrefreshable
 * session so the next person at a shared workstation never sees the previous
 * user's research, drafts, contracts, or recovery codes without a reload.
 */
type ResetFn = () => void;

const resets = new Set<ResetFn>();

/** Register a reset; returns the matching unregister (for hook-scoped state). */
export function registerReset(fn: ResetFn): () => void {
  resets.add(fn);
  return () => { resets.delete(fn); };
}

export function resetAllStores(): void {
  for (const fn of Array.from(resets)) {
    try {
      fn();
    } catch (e) {
      logger.error('store reset failed', e);
    }
  }
}
