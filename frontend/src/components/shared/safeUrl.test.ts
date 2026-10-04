import { describe, it, expect } from 'vitest';
import { safeHttpUrl } from './safeUrl';

describe('safeHttpUrl', () => {
  it('passes absolute http(s) URLs through unchanged', () => {
    expect(safeHttpUrl('https://www.courtlistener.com/opinion/1/x/')).toBe('https://www.courtlistener.com/opinion/1/x/');
    expect(safeHttpUrl('http://example.com/a?b=1#c')).toBe('http://example.com/a?b=1#c');
    expect(safeHttpUrl('  https://example.com  ')).toBe('https://example.com');
  });

  it('rejects every other scheme', () => {
    expect(safeHttpUrl('javascript:alert(1)')).toBeNull();
    expect(safeHttpUrl('data:text/html,<script>alert(1)</script>')).toBeNull();
    expect(safeHttpUrl('file:///etc/passwd')).toBeNull();
    expect(safeHttpUrl('vbscript:msgbox')).toBeNull();
  });

  it('rejects relative, empty and non-string values', () => {
    expect(safeHttpUrl('/opinion/1')).toBeNull();
    expect(safeHttpUrl('www.example.com')).toBeNull();
    expect(safeHttpUrl('')).toBeNull();
    expect(safeHttpUrl('   ')).toBeNull();
    expect(safeHttpUrl(null)).toBeNull();
    expect(safeHttpUrl(undefined)).toBeNull();
    expect(safeHttpUrl(42)).toBeNull();
  });
});
