import { create } from 'zustand';
import { registerReset } from './resetRegistry';
import { api, API_BASE_URL } from '../api';
import type { AuthorityMapResult } from '../api/types';
import type { DocAnnotation } from '../components/shared/AnnotatedDocument';
import { extractTextFromFile } from '../utils/extractText';
import { buildDocAnnotations, mappingToCitation, pushCitations } from '../utils';
import { useUIStore } from './uiStore';
import { createJobPoller, toast } from './storeUtils';
import logger from '../utils/logger';

type Status = 'idle' | 'running' | 'done' | 'error';
type FileType = 'pdf' | 'text' | null;

export interface AuthorityMapState {
  docText: string;
  docName: string;
  fileUrl: string | null;
  fileType: FileType;
  jurisdiction: string;
  filePickerOpen: boolean;
  fileLoading: boolean;
  status: Status;
  error: string | null;
  result: AuthorityMapResult | null;
  /** Result mappings grouped by document span — derived when a result lands. */
  annotations: DocAnnotation[];
  setJurisdiction: (v: string) => void;
  openFilePicker: () => void;
  closeFilePicker: () => void;
  loadUploadedFile: (file: File) => Promise<void>;
  loadIndexedDocument: (docId: string, meta: { name?: string; filename?: string }) => Promise<void>;
  clearDocument: () => void;
  run: () => Promise<void>;
  /** Ask, then delete the stored run behind the current result from the server. */
  deleteResult: () => void;
}

const jobPoller = createJobPoller();

async function convertToPdfUrl(blob: Blob, filename: string): Promise<string | null> {
  try {
    const fd = new FormData();
    fd.append('file', blob, filename);
    const resp = await api.authFetch(`${API_BASE_URL}/legal-docs/convert-to-pdf`, { method: 'POST', body: fd });
    if (resp.ok) return URL.createObjectURL(await resp.blob());
  } catch (e) {
    logger.error('docx->pdf convert failed', e);
  }
  return null;
}

export const useAuthorityMapStore = create<AuthorityMapState>((set, get) => ({
  docText: '',
  docName: '',
  fileUrl: null,
  fileType: null,
  jurisdiction: '',
  filePickerOpen: false,
  fileLoading: false,
  status: 'idle',
  error: null,
  result: null,
  annotations: [],

  setJurisdiction: (v) => set({ jurisdiction: v }),
  openFilePicker: () => set({ filePickerOpen: true }),
  closeFilePicker: () => set({ filePickerOpen: false }),

  clearDocument: () => {
    jobPoller.stop();
    const prev = get().fileUrl;
    if (prev) URL.revokeObjectURL(prev);
    set({ docText: '', docName: '', fileUrl: null, fileType: null, status: 'idle', error: null, result: null, annotations: [] });
  },

  loadUploadedFile: async (file) => {
    set({ fileLoading: true });
    const prev = get().fileUrl;
    if (prev) URL.revokeObjectURL(prev);
    set({ fileUrl: null, fileType: null });
    try {
      const ext = file.name.toLowerCase().split('.').pop() || '';
      if (ext === 'pdf') {
        set({ fileUrl: URL.createObjectURL(file), fileType: 'pdf' });
      } else if (ext === 'docx' || ext === 'doc') {
        const url = await convertToPdfUrl(file, file.name);
        if (url) set({ fileUrl: url, fileType: 'pdf' });
        else set({ fileType: 'text' });
      } else {
        set({ fileType: 'text' });
      }

      toast(`Extracting text from ${file.name}…`, 'info');
      const text = await extractTextFromFile(file);
      if (!text) {
        toast('Could not extract text from that file.', 'error');
        return;
      }
      set({ docText: text, docName: file.name.replace(/\.[^.]+$/, ''), status: 'idle', result: null, error: null });
      toast(`Loaded ${file.name}`, 'success');
    } catch (e) {
      logger.error('upload extract failed', e);
      toast('Failed to read that file.', 'error');
    } finally {
      set({ fileLoading: false });
    }
  },

  loadIndexedDocument: async (docId, meta) => {
    set({ fileLoading: true });
    const prev = get().fileUrl;
    if (prev) URL.revokeObjectURL(prev);
    set({ fileUrl: null, fileType: null });
    try {
      const res = await api.getDocumentContent(docId);
      set({
        docText: res.text,
        docName: meta.name || meta.filename || res.filename?.replace(/\.[^.]+$/, '') || 'Document',
        status: 'idle',
        result: null,
        error: null,
        filePickerOpen: false,
      });

      // Fetch the raw file for visual rendering.
      try {
        const fileResp = await api.authFetch(`${API_BASE_URL}/documents/${docId}/file`);
        if (fileResp.ok) {
          const blob = await fileResp.blob();
          const ext = (res.filename || '').toLowerCase().split('.').pop() || '';
          if (blob.type === 'application/pdf' || ext === 'pdf') {
            set({ fileUrl: URL.createObjectURL(blob), fileType: 'pdf' });
          } else if (ext === 'docx' || ext === 'doc') {
            const url = await convertToPdfUrl(blob, res.filename || 'document.docx');
            if (url) set({ fileUrl: url, fileType: 'pdf' });
            else set({ fileType: 'text' });
          } else {
            set({ fileType: 'text' });
          }
        } else {
          set({ fileType: 'text' });
        }
      } catch (fileErr) {
        logger.error('file fetch for visual render failed', fileErr);
        set({ fileType: 'text' });
      }

      toast(`Loaded ${res.filename}`, 'success');
    } catch (e) {
      logger.error('load indexed doc failed', e);
      toast('Failed to load document.', 'error');
    } finally {
      set({ fileLoading: false });
    }
  },

  run: async () => {
    const { docText, docName, jurisdiction } = get();
    if (!docText.trim()) return;
    jobPoller.stop();
    set({ status: 'running', error: null, result: null, annotations: [] });

    try {
      const { job_id } = await api.submitAuthorityMap({
        documentText: docText,
        documentName: docName.trim() || null,
        jurisdiction: jurisdiction.trim() || null,
      });

      jobPoller.start({
        fetchJob: () => api.getAuthorityMapJob(job_id),
        maxAttempts: 150,
        failedMessage: 'Mapping failed.',
        timeoutMessage: 'Timed out waiting for results.',
        onCompleted: (job) => {
          const result = job.result ?? null;
          set({ status: 'done', result, annotations: buildDocAnnotations(result?.mappings ?? []) });
          // Surface authorities in the Sources tab — that panel is the
          // single home for citations (verified first; unverified stay
          // reachable there for review instead of in an extra inline panel).
          if (result?.mappings?.length) {
            const ordered = [...result.mappings].sort((a, b) => Number(b.verified) - Number(a.verified));
            pushCitations(ordered.map((m, i) => mappingToCitation(m, i)));
            useUIStore.getState().setRightPanelTab('sources');
          }
        },
        onFailed: (message) => set({ status: 'error', error: message }),
      });
    } catch (e) {
      logger.error('authority map submit failed', e);
      set({ status: 'error', error: e instanceof Error ? e.message : 'Failed to start mapping.' });
    }
  },

  deleteResult: () => {
    const runId = get().result?.run_id;
    if (!runId) return;
    useUIStore.getState().showConfirm({
      title: 'Delete this citation map?',
      message: 'The stored map, including the quotes taken from your document, is permanently deleted from the server. The document itself is not affected.',
      type: 'danger',
      confirmText: 'Delete map',
      onConfirm: async () => {
        try {
          await api.deleteAuthorityMap(runId);
          // Only clear if the user has not started another run meanwhile.
          if (get().result?.run_id === runId) {
            set({ status: 'idle', result: null, annotations: [], error: null });
          }
          toast('Citation map deleted.', 'success');
        } catch (e) {
          logger.error('authority map delete failed', e);
          toast(e instanceof Error ? e.message : 'Could not delete the citation map.', 'error');
        }
      },
    });
  },
}));

registerReset(() => {
  jobPoller.stop();
  const url = useAuthorityMapStore.getState().fileUrl;
  if (url) URL.revokeObjectURL(url);
  useAuthorityMapStore.setState(useAuthorityMapStore.getInitialState(), true);
});
