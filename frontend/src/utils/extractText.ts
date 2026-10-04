import { api, API_BASE_URL } from '../api';
import { useUIStore } from '../stores/uiStore';
import logger from './logger';

/**
 * Standalone utility to extract text from an uploaded file via the backend.
 * Uses the uiStore for toast notifications instead of requiring an addToast param.
 */
export async function extractTextFromFile(file: File): Promise<string | null> {
  const formData = new FormData();
  formData.append('file', file);
  try {
    const response = await api.authFetch(`${API_BASE_URL}/legal-docs/extract-text`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) throw new Error('Failed to extract text from file');
    const data = await response.json();
    return data.text;
  } catch (err) {
    logger.error('Text extraction error:', err);
    useUIStore.getState().addToast(`Failed to extract text from ${file.name}`, 'error');
    return null;
  }
}
