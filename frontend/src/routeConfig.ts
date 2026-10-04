/**
 * Route configuration: maps URL paths to mode IDs and vice versa.
 */
const ROUTE_TO_MODE: Record<string, string> = {
  '/research': 'research',
  '/documents': 'rag-docs',
  '/judge-intel': 'judge-intel',
  '/case-citations': 'case-citations',
  '/contracts': 'contracts',
  '/drafting': 'drafting',
  '/case': 'case',
};

export const MODE_TO_ROUTE: Record<string, string> = {
  'research': '/research',
  'rag-docs': '/documents',
  'judge-intel': '/judge-intel',
  'case-citations': '/case-citations',
  'contracts': '/contracts',
  'drafting': '/drafting',
  'case': '/case',
};

/**
 * Derive the activeMode string from a pathname.
 */
export function modeFromPath(pathname: string): string {
  // /case and /case/:id — but not /case-citations, which has its own entry.
  if (pathname === '/case' || pathname.startsWith('/case/')) return 'case';
  return ROUTE_TO_MODE[pathname] || 'research';
}
