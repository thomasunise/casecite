import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('logger', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('exposes debug, info, warn, error methods', async () => {
    const { default: logger } = await import('./logger.js');
    expect(typeof logger.debug).toBe('function');
    expect(typeof logger.info).toBe('function');
    expect(typeof logger.warn).toBe('function');
    expect(typeof logger.error).toBe('function');
  });

  it('error always calls console.error regardless of mode', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { default: logger } = await import('./logger.js');
    logger.error('test error');
    expect(spy).toHaveBeenCalledWith('test error');
    spy.mockRestore();
  });

  it('debug/info/warn call console in dev mode (Vitest sets DEV=true)', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {});
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { default: logger } = await import('./logger.js');

    logger.debug('d');
    logger.info('i');
    logger.warn('w');

    expect(logSpy).toHaveBeenCalledWith('d');
    expect(infoSpy).toHaveBeenCalledWith('i');
    expect(warnSpy).toHaveBeenCalledWith('w');

    logSpy.mockRestore();
    infoSpy.mockRestore();
    warnSpy.mockRestore();
  });
});
