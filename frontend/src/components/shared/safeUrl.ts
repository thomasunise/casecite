/**
 * Returns `value` when it is an absolute http(s) URL, otherwise null.
 *
 * Backend-supplied links (CourtListener, Wikipedia, citation notes) pass
 * through this before landing in an `href`, so a `javascript:` or `data:`
 * string can never become a clickable link — it simply renders as text.
 */
export function safeHttpUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return null;
  }
  return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? trimmed : null;
}
