/** Generate unique ID */
export const generateId = (): string => Math.random().toString(36).substr(2, 9);

/** Format file size in human-readable form */
export const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

/**
 * Parse a backend timestamp as UTC.
 * Server datetimes are naive UTC (no timezone suffix); parsing them directly
 * would treat them as local time, skewing displayed times by the UTC offset.
 */
export const parseUtcDate = (timestamp: string): Date => {
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(timestamp);
  return new Date(hasZone ? timestamp : timestamp + 'Z');
};

/** Read a cookie by name */
export function getCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)')
  );
  return match ? decodeURIComponent(match[1]) : null;
}
