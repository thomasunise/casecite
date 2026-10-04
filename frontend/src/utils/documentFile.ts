import { api, API_BASE_URL } from '../api';
import logger from './logger';

/**
 * Fetch a knowledge-base file as a browser-renderable PDF object URL, so
 * viewers can show the document with its real formatting instead of the
 * extracted plain text. PDFs come back directly; Word documents go through
 * the server's convert-to-pdf endpoint; anything else returns null (text
 * view only). The caller owns the URL and must revokeObjectURL it.
 */
export async function fetchDocumentPdfUrl(
  docId: string,
  filename?: string | null,
): Promise<string | null> {
  try {
    const resp = await api.authFetch(`${API_BASE_URL}/documents/${docId}/file`);
    if (!resp.ok) return null;
    const blob = await resp.blob();
    const ext = (filename || '').toLowerCase().split('.').pop() || '';
    const isWord =
      ext === 'docx' || ext === 'doc' ||
      blob.type.includes('wordprocessingml') || blob.type.includes('msword');
    if (blob.type === 'application/pdf' || ext === 'pdf') {
      return URL.createObjectURL(blob);
    }
    if (isWord) {
      const fd = new FormData();
      fd.append('file', blob, filename || 'document.docx');
      const conv = await api.authFetch(`${API_BASE_URL}/legal-docs/convert-to-pdf`, {
        method: 'POST',
        body: fd,
      });
      if (conv.ok) return URL.createObjectURL(await conv.blob());
    }
    return null;
  } catch (e) {
    logger.error('Document file fetch for native view failed:', e);
    return null;
  }
}
