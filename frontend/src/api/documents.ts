import { api } from './client';
import type { DocumentContent, DocumentInfo, DocumentListResponse, DocumentTree, MessageResponse } from './types';

Object.assign(api, {
  async uploadDocument(file: File): Promise<DocumentInfo> {
    const formData = new FormData();
    formData.append('file', file);

    // Indexing is synchronous server-side (extraction, OCR, chunking,
    // embeddings) — the default 30s timeout aborts real-world PDFs mid-index
    // while the server finishes anyway, stranding the UI on "Uploading...".
    return api.request('/documents', { method: 'POST', body: formData, timeout: 300000 });
  },

  async getDocuments(limit: number = 50, offset: number = 0): Promise<DocumentListResponse> {
    return api.request(`/documents?limit=${limit}&offset=${offset}`);
  },

  async getDocumentTree(): Promise<DocumentTree> {
    return api.request('/documents/tree');
  },

  async getDocumentContent(documentId: string): Promise<DocumentContent> {
    return api.request(`/documents/${documentId}/content`);
  },

  async deleteDocument(documentId: string): Promise<MessageResponse> {
    return api.request(`/documents/${documentId}`, { method: 'DELETE' });
  },

  // ── Knowledge-base folders ──────────────────────────────────────
  async listFolders(): Promise<{ folders: string[] }> {
    return api.request('/documents/folders');
  },

  async createFolder(name: string): Promise<{ path: string; folders: string[] }> {
    return api.request('/documents/folders', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  },

  async deleteFolder(path: string): Promise<{ status: string; folders: string[] }> {
    return api.request(`/documents/folders?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
  },

  async moveDocument(documentId: string, folderPath: string | null): Promise<{ status: string }> {
    return api.request(`/documents/${documentId}/move`, {
      method: 'POST',
      body: JSON.stringify({ folder_path: folderPath }),
    });
  },
});
