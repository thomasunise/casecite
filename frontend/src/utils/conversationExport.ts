import { api } from '../api';
import type { ConversationExportFormat, ConversationExportMessage } from '../api/types';
import { useUIStore } from '../stores/uiStore';
import { downloadBlob } from './downloadBlob';
import logger from './logger';

const EXT: Record<ConversationExportFormat, string> = { docx: 'docx', pdf: 'pdf', md: 'md' };

/** Filename-safe stem from a title; the server picks its own too, this is the fallback. */
function exportFileStem(title: string): string {
  const stem = title.replace(/[^\w\s-]+/g, '').trim().replace(/\s+/g, '-').slice(0, 60).replace(/^-+|-+$/g, '');
  return stem || 'conversation';
}

/** A title for a transcript: the first question, trimmed, or the page's own label. */
export function conversationTitle(fallback: string, firstUserText?: string | null): string {
  const q = (firstUserText || '').replace(/\s+/g, ' ').trim();
  if (!q) return fallback;
  return q.length > 70 ? `${q.slice(0, 67).trimEnd()}…` : q;
}

/**
 * Render a transcript server-side and download it. Toasts on success and
 * failure so stores only need to wrap it with their busy flag.
 */
export async function downloadConversation(
  title: string,
  messages: ConversationExportMessage[],
  format: ConversationExportFormat,
): Promise<void> {
  const toast = useUIStore.getState().addToast;
  if (messages.length === 0) {
    toast('Nothing to export yet.', 'info');
    return;
  }
  try {
    const blob = await api.exportConversation({ title, format, messages });
    downloadBlob(blob, `${exportFileStem(title)}.${EXT[format]}`);
    toast(format === 'docx' ? 'Word document downloaded.' : format === 'pdf' ? 'PDF downloaded.' : 'Markdown downloaded.', 'success');
  } catch (e) {
    logger.error('conversation export failed', e);
    toast(e instanceof Error ? e.message : 'Export failed.', 'error');
  }
}
