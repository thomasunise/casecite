const pending = new Map<string, Promise<void>>();

/**
 * Load a third-party script once. Rejects on a network/CSP failure (and
 * forgets the attempt, so a retry can succeed) — a loader that only handles
 * `onload` leaves its caller's spinner hanging forever when the script is
 * blocked or the user is offline.
 */
export function loadScript(
  src: string,
  { id, attributes }: { id?: string; attributes?: Record<string, string> } = {},
): Promise<void> {
  const existing = pending.get(src);
  if (existing) return existing;

  const promise = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.async = true;
    if (id) script.id = id;
    for (const [name, value] of Object.entries(attributes ?? {})) script.setAttribute(name, value);
    script.onload = () => resolve();
    script.onerror = () => {
      pending.delete(src);
      script.remove();
      reject(new Error(`Could not load ${new URL(src, window.location.href).host}. Check your connection or content blocker and try again.`));
    };
    document.body.appendChild(script);
  });
  pending.set(src, promise);
  return promise;
}
