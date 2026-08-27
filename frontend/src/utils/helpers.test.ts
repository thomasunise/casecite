import { describe, it, expect } from 'vitest';
import { generateId, formatFileSize, getCookie } from './helpers';

describe('generateId', () => {
  it('returns a non-empty string', () => {
    const id = generateId();
    expect(typeof id).toBe('string');
    expect(id.length).toBeGreaterThan(0);
  });

  it('returns unique values on successive calls', () => {
    const ids = new Set(Array.from({ length: 50 }, () => generateId()));
    expect(ids.size).toBe(50);
  });
});

describe('formatFileSize', () => {
  it('formats bytes', () => {
    expect(formatFileSize(500)).toBe('500 B');
  });

  it('formats kilobytes', () => {
    expect(formatFileSize(2048)).toBe('2.0 KB');
  });

  it('formats megabytes', () => {
    expect(formatFileSize(5 * 1024 * 1024)).toBe('5.0 MB');
  });

  it('handles zero', () => {
    expect(formatFileSize(0)).toBe('0 B');
  });

  it('handles boundary at 1 KB', () => {
    expect(formatFileSize(1024)).toBe('1.0 KB');
  });
});

describe('getCookie', () => {
  it('returns null when no cookies exist', () => {
    expect(getCookie('missing')).toBeNull();
  });

  it('reads a cookie by name', () => {
    document.cookie = 'session=abc123';
    expect(getCookie('session')).toBe('abc123');
  });

  it('decodes URI-encoded values', () => {
    document.cookie = 'data=' + encodeURIComponent('hello world');
    expect(getCookie('data')).toBe('hello world');
  });

  it('returns null for a non-existent cookie among existing ones', () => {
    document.cookie = 'a=1';
    expect(getCookie('b')).toBeNull();
  });
});
