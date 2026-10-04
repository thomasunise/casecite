import { describe, it, expect, afterEach } from 'vitest';
import { loadScript } from './loadScript';

function lastScript(): HTMLScriptElement {
  const scripts = document.body.querySelectorAll('script');
  return scripts[scripts.length - 1];
}

describe('loadScript', () => {
  afterEach(() => {
    document.body.querySelectorAll('script').forEach((s) => s.remove());
  });

  it('resolves on load and reuses the same request for the same URL', async () => {
    const first = loadScript('https://cdn.example/a.js', { id: 'a', attributes: { 'data-app-key': 'k' } });
    const second = loadScript('https://cdn.example/a.js');
    expect(second).toBe(first);
    expect(document.body.querySelectorAll('script')).toHaveLength(1);
    const script = lastScript();
    expect(script.id).toBe('a');
    expect(script.getAttribute('data-app-key')).toBe('k');
    script.onload?.(new Event('load'));
    await expect(first).resolves.toBeUndefined();
  });

  it('rejects when the script fails to load, and allows a retry', async () => {
    const attempt = loadScript('https://cdn.example/blocked.js');
    lastScript().onerror?.(new Event('error'));
    await expect(attempt).rejects.toThrow('Could not load cdn.example');
    expect(document.body.querySelectorAll('script')).toHaveLength(0);

    const retry = loadScript('https://cdn.example/blocked.js');
    expect(retry).not.toBe(attempt);
    lastScript().onload?.(new Event('load'));
    await expect(retry).resolves.toBeUndefined();
  });
});
