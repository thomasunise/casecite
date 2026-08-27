import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import { api } from '../api';
import { useUIStore } from '../stores/uiStore';
import { registerReset } from '../stores/resetRegistry';
import { generateId, parseUtcDate, mappingToCitation, fetchDocumentPdfUrl } from '../utils';
import { parseCitations } from '../utils/citationParser';
import logger from '../utils/logger';
import type { ChatMessage, Citation, SessionStats, DocumentFilter, RagSettings, ChatStats } from '../types';
import type { ChatSessionSummary, ChatSessionMessage, StrategyBriefResponse, AuthorityMapChatResult, AuthorityMapping } from '../api/types';
import type { DocAnnotation } from '../components/shared/AnnotatedDocument';
import { setCitationsSink } from '../utils/citationsBridge';
import { conversationTitle, downloadConversation } from '../utils/conversationExport';
import type { ConversationExportFormat, ConversationExportMessage } from '../api/types';

/** Flatten a Matter Strategy message (brief / authority map included) for export. */
function researchMessageToExport(msg: ChatMessage): ConversationExportMessage {
  if (msg.type === 'user') return { role: 'user', text: msg.content };
  const parts: string[] = [];
  if (msg.strategy) {
    const b = msg.strategy;
    if (b.position) parts.push('## Position', b.position);
    const section = (label: string, pts: { point?: string; step?: string }[]) => {
      if (!pts?.length) return;
      parts.push(`## ${label}`);
      for (const p of pts) parts.push(`- ${p.point || p.step || ''}`);
    };
    section('Strengths', b.strengths);
    section('Weaknesses', b.weaknesses);
    section('Next steps', b.next_steps);
  } else if (msg.authorityMap) {
    const t = msg.authorityMap.totals;
    parts.push(`Authority map: ${t.propositions} propositions, ${t.authorities} authorities, ${t.verified} verified across ${t.files} file(s).`);
    if (msg.content) parts.push(msg.content);
  } else {
    parts.push(msg.content);
  }
  return {
    role: 'assistant',
    text: parts.join('\n\n'),
    citations: (msg.citations || []).map((c) => ({
      label: c.reference || c.source,
      quote: c.passage || null,
      url: c.url || null,
    })),
  };
}

/** A knowledge-base file opened as a viewer tab in the workspace. */
export interface OpenDoc {
  id: string;
  filename: string;
  text: string;
  loading: boolean;
  /** Object URL of the file rendered as PDF (native formatting), when available. */
  fileUrl: string | null;
}

/** Poll a chat-triggered authority-map job to completion (~20 min budget —
    it reads every scoped file and verifies each authority against the real
    opinion text). */
async function pollAuthorityMapChatJob(jobId: string): Promise<AuthorityMapChatResult> {
  for (let attempt = 0; attempt < 400; attempt++) {
    const job = await api.getChatAuthorityMapJob(jobId);
    if (job.status === 'completed') {
      if (!job.result) throw new Error('The authority map returned no result.');
      return job.result;
    }
    if (job.status === 'failed' || job.status === 'cancelled') {
      throw new Error(job.error || 'Authority mapping failed.');
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error('Timed out waiting for the authority map.');
}

/** Map a persisted session message's stats JSON into the ChatMessage stats shape. */
function mapStoredStats(stats: Record<string, unknown> | null, citationCount: number): ChatStats | undefined {
  if (!stats) return undefined;
  return {
    docsSearched: (stats.docs_searched as number) || 0,
    chunksRetrieved: (stats.chunks_retrieved as number) || citationCount,
    processingTime: (stats.processing_time as string) || '',
    caseLawSearched: (stats.case_law_searched as number) || 0,
    caseLawIncluded: (stats.case_law_included as number) || 0,
  };
}

/**
 * Custom hook encapsulating chat/research state and handlers:
 * messages, citations, persistent chat sessions, session stats, and
 * search-scope controls.
 *
 * @param {Object} params
 * @param {Function} params.addToast
 * @param {Object}   params.ragSettings        - Current RAG configuration
 * @param {string}   params.activeMode         - Current navigation mode
 * @param {Function} params.setActiveMode      - Mode setter (for history click)
 */
export function useResearchState({ addToast, ragSettings, activeMode, setActiveMode }: { addToast: (msg: string, type?: string) => void; ragSettings: RagSettings; activeMode: string; setActiveMode: (mode: string) => void }) {
  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [exportingConversation, setExportingConversation] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStage, setProcessingStage] = useState('');

  // Citations. The Sources panel accumulates per-exchange within the ACTIVE
  // conversation — every question keeps its own group (tagged messageId +
  // sourceQuery) so five questions mean five groups. It resets on clear/new
  // chat and rebuilds on session load; it never persists on its own — stale
  // citations from dead sessions must not haunt the panel.
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [allCitations, setAllCitations] = useState<Citation[]>([]);
  const [citationFilter, setCitationFilter] = useState('all');

  // Stores (e.g. authorityMapStore) surface citations into the Sources panel
  // through this sink — registered like the shared navigate reference in
  // utils/router.ts. Merges by id so a re-run never duplicates rows.
  useEffect(() => {
    setCitationsSink((citations: Citation[]) => {
      setAllCitations((prev: Citation[]) => {
        const existing = new Set(prev.map((c: Citation) => c.id));
        const fresh = citations.filter((c: Citation) => !existing.has(c.id));
        return fresh.length ? [...prev, ...fresh] : prev;
      });
    });
    return () => setCitationsSink(null);
  }, []);

  // Jump-to-answer anchor: the Sources panel sets this; the view scrolls the
  // conversation to that message (opening the chat dock if minimized).
  const [pendingMessageJump, setPendingMessageJump] = useState<{ id: string; seq: number } | null>(null);
  const jumpToMessage = useCallback((id: string) => {
    setPendingMessageJump({ id, seq: Date.now() });
  }, []);

  // Hover link between the chat's numbered source pills and the Sources
  // panel rows: hovering a pill spotlights its row.
  const [hoveredCitationId, setHoveredCitationId] = useState<string | null>(null);

  // Persistent chat sessions. The active conversation is stored server-side;
  // currentSessionId is null until the first response creates a session.
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSessionSummary[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const sessionsLoadedRef = useRef(false);

  // Session stats
  const [sessionStats, setSessionStats] = useState<SessionStats>({
    queries: 0, citations: 0, approved: 0, rejected: 0, pending: 0,
  });

  // Scope is the only client-side control (set from the file workspace —
  // null = all documents, the default); intent (ask vs strategy vs authority
  // map) and case-law augmentation are decided server-side per message.
  const [mainDocFilter, setMainDocFilter] = useState<DocumentFilter | null>(null);

  // Refs. lastMessageRef is attached to the NEWEST message row — the app
  // scrolls to its TOP when a message lands, so long answers read from the
  // start instead of dumping the user at the bottom.
  const lastMessageRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Open document viewers: files opened from the workspace render as a
  // full-screen split view (1 = full, 2 = 50/50, 4 = quartered) with
  // case-law anchors from authority-map results.
  const [openDocs, setOpenDocs] = useState<OpenDoc[]>([]);

  const openDocument = useCallback(async (docId: string, filename: string) => {
    let alreadyOpen = false;
    setOpenDocs((prev: OpenDoc[]) => {
      alreadyOpen = prev.some((d) => d.id === docId);
      return alreadyOpen
        ? prev
        : [...prev, { id: docId, filename, text: '', loading: true, fileUrl: null }];
    });
    if (alreadyOpen) return;
    try {
      // Text (for anchors) and the native file render (real formatting) load
      // together; the pane defaults to the native view when it exists.
      const [res, fileUrl] = await Promise.all([
        api.getDocumentContent(docId),
        fetchDocumentPdfUrl(docId, filename),
      ]);
      setOpenDocs((prev: OpenDoc[]) => prev.map((d) =>
        d.id === docId
          ? { ...d, text: res.text, filename: res.filename || filename, fileUrl, loading: false }
          : d
      ));
    } catch (e: unknown) {
      logger.error('Failed to open document:', e);
      addToast('Could not open that file.', 'error');
      setOpenDocs((prev: OpenDoc[]) => prev.filter((d) => d.id !== docId));
    }
  }, [addToast]);

  const closeDocument = useCallback((docId: string) => {
    setOpenDocs((prev: OpenDoc[]) => {
      const target = prev.find((d) => d.id === docId);
      if (target?.fileUrl) URL.revokeObjectURL(target.fileUrl);
      return prev.filter((d) => d.id !== docId);
    });
  }, []);

  // Citation tracing: open the cited file (in the text view) and scroll to
  // the exact verified span, highlighted — set from the citation modal.
  const [pendingDocJump, setPendingDocJump] = useState<{ docId: string; start: number; seq: number } | null>(null);
  const jumpToDocumentSpan = useCallback((docId: string, filename: string, start: number) => {
    void openDocument(docId, filename);
    setPendingDocJump({ docId, start, seq: Date.now() });
  }, [openDocument]);

  // Sign-out wipes the conversation, its sources, and any open document
  // blobs — research state lives in this hook, not a store, so it registers
  // with the same registry the stores use.
  useEffect(() => registerReset(() => {
    setMessages([]);
    setInputValue('');
    setIsProcessing(false);
    setProcessingStage('');
    setSelectedCitation(null);
    setAllCitations([]);
    setCitationFilter('all');
    setPendingMessageJump(null);
    setHoveredCitationId(null);
    setCurrentSessionId(null);
    setChatSessions([]);
    setIsLoadingSessions(false);
    sessionsLoadedRef.current = false;
    setSessionStats({ queries: 0, citations: 0, approved: 0, rejected: 0, pending: 0 });
    setMainDocFilter(null);
    setOpenDocs((prev: OpenDoc[]) => {
      for (const d of prev) if (d.fileUrl) URL.revokeObjectURL(d.fileUrl);
      return [];
    });
    setPendingDocJump(null);
  }), []);

  // Anchors per document, grouped by span — the shape the annotated document
  // renderer uses. Two feeds: authority-map mappings (case law per
  // proposition) and claim-grounded chat citations (the answer's claims with
  // verbatim-verified quotes), so an opened file shows every verified anchor
  // from the conversation.
  const docAnnotations = useMemo(() => {
    const mappingsByDoc: Record<string, AuthorityMapping[]> = {};
    for (const msg of messages) {
      for (const f of msg.authorityMap?.files ?? []) {
        if (!f.document_id) continue;
        (mappingsByDoc[f.document_id] ||= []).push(...f.mappings);
      }
      for (const c of msg.citations ?? []) {
        if (!c.document_id || c.docSpanStart == null || c.docSpanEnd == null) continue;
        (mappingsByDoc[c.document_id] ||= []).push({
          proposition: c.reasoning?.[0]?.description || c.logic?.application || 'Cited claim',
          doc_quote: c.passage,
          doc_span_start: c.docSpanStart,
          doc_span_end: c.docSpanEnd,
          source: 'internal',
          case_name: c.source,
          citation: null,
          source_ref: null,
          source_url: null,
          support_quote: c.passage,
          source_span_start: null,
          source_span_end: null,
          verified: c.verified ?? true,
          relevance: (c.confidence || 0) / 100,
          note: null,
          reasoning: { steps: [], application: c.logic?.application || null },
        });
      }
    }
    const out: Record<string, DocAnnotation[]> = {};
    for (const [docId, ms] of Object.entries(mappingsByDoc)) {
      const byKey = new Map<string, DocAnnotation>();
      for (const m of ms) {
        if (m.doc_span_start == null || m.doc_span_end == null) continue;
        const key = `${m.doc_span_start}:${m.doc_span_end}`;
        if (!byKey.has(key)) byKey.set(key, { start: m.doc_span_start, end: m.doc_span_end, mappings: [] });
        byKey.get(key)!.mappings.push(m);
      }
      out[docId] = [...byKey.values()];
    }
    return out;
  }, [messages]);

  // Refresh the server-side session list (History tab data).
  const loadChatSessions = useCallback(async () => {
    setIsLoadingSessions(true);
    try {
      const response = await api.listChatSessions();
      setChatSessions(response.sessions || []);
      sessionsLoadedRef.current = true;
    } catch (error: unknown) {
      logger.debug('Could not load chat sessions:', error instanceof Error ? error.message : String(error));
    }
    setIsLoadingSessions(false);
  }, []);

  // Lazy-load sessions the first time the History tab opens.
  const rightPanelTab = useUIStore(st => st.rightPanelTab);
  useEffect(() => {
    if (rightPanelTab === 'history' && !sessionsLoadedRef.current) {
      loadChatSessions();
    }
  }, [rightPanelTab, loadChatSessions]);

  // Send message
  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isProcessing) return;

    const query = inputValue.trim();
    setInputValue('');
    setIsProcessing(true);

    const userMsg: ChatMessage = { id: generateId(), type: 'user' as const, content: query, timestamp: new Date() };
    setMessages((prev: ChatMessage[]) => [...prev, userMsg]);

    const startTime = Date.now();

    const stages = ['Thinking...', 'Analyzing documents...', 'Searching knowledge base...', 'Generating response...'];
    let stageIndex = 0;
    setProcessingStage(stages[0]);
    const stageInterval = setInterval(() => {
      stageIndex = (stageIndex + 1) % stages.length;
      setProcessingStage(stages[stageIndex]);
    }, 2000);

    try {
      const response = await api.query(query, activeMode, {
        topK: ragSettings.topK,
        similarityThreshold: ragSettings.similarityThreshold,
        includeDocuments: true,
        documentFilter: mainDocFilter as unknown as string | null,
        sessionId: currentSessionId,
      });

      clearInterval(stageInterval);

      // Chat-triggered authority map: the backend submitted a background job.
      // Show its acknowledgement, poll the job, then post the audit result as
      // its own message with every authority in the Sources panel.
      if (response.authority_map_job?.job_id) {
        const jobInfo = response.authority_map_job;
        setMessages((prev: ChatMessage[]) => [...prev, {
          id: response.id || generateId(),
          type: 'assistant' as const,
          content: response.content || 'Mapping supporting case law…',
          timestamp: new Date(),
          citations: [],
          mode: activeMode,
        }]);
        if (response.session_id) setCurrentSessionId(response.session_id);
        setProcessingStage(
          `Mapping case law across ${jobInfo.documents.length} file${jobInfo.documents.length === 1 ? '' : 's'}…`
        );
        const mapResult = await pollAuthorityMapChatJob(jobInfo.job_id);
        const mapMsgId = generateId();
        const mapCitations: Citation[] = [];
        mapResult.files.forEach((f, fi) => {
          [...f.mappings]
            .sort((a, b) => Number(b.verified) - Number(a.verified))
            .forEach((m, i) => mapCitations.push({
              ...mappingToCitation(m, i, `am${fi}`),
              messageId: mapMsgId,
              sourceQuery: query,
            }));
        });
        const t = mapResult.totals;
        const resultMsg: ChatMessage = {
          id: mapMsgId,
          type: 'assistant' as const,
          content: `Authority map complete: ${t.verified} verified authorit${t.verified === 1 ? 'y' : 'ies'} across ${t.propositions} proposition${t.propositions === 1 ? '' : 's'} in ${t.files} file${t.files === 1 ? '' : 's'}. Every authority is in the Sources panel — click one to review the verified quote.`,
          timestamp: new Date(),
          citations: mapCitations,
          mode: activeMode,
          authorityMap: mapResult,
          stats: {
            docsSearched: t.files,
            chunksRetrieved: 0,
            processingTime: ((Date.now() - startTime) / 1000).toFixed(0) + 's',
            caseLawSearched: t.authorities,
            caseLawIncluded: t.verified,
          },
        };
        setMessages((prev: ChatMessage[]) => [...prev, resultMsg]);
        setAllCitations((prev: Citation[]) => [...prev, ...mapCitations]);
        setSessionStats((prev: SessionStats) => ({
          ...prev,
          queries: prev.queries + 1,
          citations: prev.citations + mapCitations.length,
          pending: prev.pending + mapCitations.length,
        }));
        setIsProcessing(false);
        setProcessingStage('');
        return;
      }

      const processingTime = ((Date.now() - startTime) / 1000).toFixed(2);

      const msgId = response.id || generateId();
      const citations: Citation[] = parseCitations(response.citations || [], query)
        .map((c: Citation) => ({ ...c, messageId: msgId, sourceQuery: query }));

      const strategy = (response as { strategy?: import('../api/types').StrategyBriefResponse }).strategy ?? undefined;
      const assistantMsg: ChatMessage = {
        id: msgId,
        type: 'assistant' as const,
        content: response.content || 'No response generated.',
        timestamp: new Date(),
        citations: citations,
        mode: activeMode,
        strategy,
        stats: {
          docsSearched: (response.stats?.docs_searched as number) || 0,
          chunksRetrieved: (response.stats?.chunks_retrieved as number) || citations.length,
          processingTime: (response.stats?.processing_time as string) || processingTime + 's',
          caseLawSearched: (response.stats?.case_law_searched as number) || 0,
          caseLawIncluded: (response.stats?.case_law_included as number) || 0,
        },
      };

      setMessages((prev: ChatMessage[]) => [...prev, assistantMsg]);
      setAllCitations((prev: Citation[]) => [...prev, ...citations]);
      setSessionStats((prev: SessionStats) => ({
        ...prev,
        queries: prev.queries + 1,
        citations: prev.citations + citations.length,
        pending: prev.pending + citations.length,
      }));

      // Adopt the server-side session (created on first exchange) and keep
      // the History tab in sync once it has been loaded.
      if (response.session_id) {
        setCurrentSessionId(response.session_id);
        if (sessionsLoadedRef.current) loadChatSessions();
      }

    } catch (error: unknown) {
      clearInterval(stageInterval);
      logger.error('RAG query error:', error);
      addToast(error instanceof Error ? error.message : 'Query failed', 'error');

      const errorMsg: ChatMessage = {
        id: generateId(),
        type: 'assistant',
        content: `**Error**\n\nFailed to process your query: ${error instanceof Error ? error.message : 'Unknown error'}\n\nIf you see "No LLM configured", please click the **Settings** button in the header and enter an API key (OpenAI, Anthropic, or Google) in the API Keys tab.`,
        timestamp: new Date(),
        citations: [],
        mode: activeMode,
        isError: true,
      };

      setMessages((prev: ChatMessage[]) => [...prev, errorMsg]);
      setAllCitations([]);
    }

    setIsProcessing(false);
    setProcessingStage('');
  }, [inputValue, isProcessing, activeMode, ragSettings, mainDocFilter, currentSessionId, addToast, loadChatSessions]);

  // Citation status update
  const handleCitationUpdate = useCallback((citationId: string, status: string, notes: string) => {
    setAllCitations((prev: Citation[]) => prev.map((c: Citation) => c.id === citationId ? {...c, status: status as Citation['status'], notes, reviewedAt: new Date()} : c));
    setMessages((prev: ChatMessage[]) => prev.map((msg: ChatMessage) => ({
      ...msg,
      citations: msg.citations?.map((c: Citation) => c.id === citationId ? {...c, status: status as Citation['status'], notes} : c)
    })));
    setSessionStats((prev: SessionStats) => {
      const oldStatus = allCitations.find((c: Citation) => c.id === citationId)?.status || 'pending';
      const prevRecord = prev as unknown as Record<string, number>;
      return {
        ...prev,
        [oldStatus]: Math.max(0, prevRecord[oldStatus] - 1),
        [status]: prevRecord[status] + 1,
      };
    });
  }, [allCitations]);

  // Reopen a persisted conversation from the History tab.
  const loadSession = useCallback(async (sessionId: string) => {
    try {
      const detail = await api.getChatSession(sessionId);

      let lastUserQuery = '';
      let queries = 0;
      const restoredCitations: Citation[] = [];
      const mapped: ChatMessage[] = detail.messages.map((m: ChatSessionMessage) => {
        if (m.role === 'user') {
          lastUserQuery = m.content;
          queries += 1;
          return {
            id: m.id,
            type: 'user' as const,
            content: m.content,
            timestamp: parseUtcDate(m.created_at),
          };
        }
        const citations = parseCitations(m.citations || [], lastUserQuery)
          .map((c: Citation) => ({ ...c, messageId: m.id, sourceQuery: lastUserQuery }));
        restoredCitations.push(...citations);
        return {
          id: m.id,
          type: 'assistant' as const,
          content: m.content,
          timestamp: parseUtcDate(m.created_at),
          citations,
          mode: 'research',
          strategy: (m.strategy as StrategyBriefResponse | null) ?? undefined,
          stats: mapStoredStats(m.stats, citations.length),
        };
      });

      setMessages(mapped);
      // Rebuild the Sources panel's per-question groups for the whole session.
      setAllCitations(restoredCitations);
      setSelectedCitation(null);
      setCurrentSessionId(detail.id);
      setSessionStats({
        queries,
        citations: restoredCitations.length,
        approved: 0,
        rejected: 0,
        pending: restoredCitations.length,
      });
      setActiveMode('research');
    } catch (error: unknown) {
      logger.error('Failed to load chat session:', error);
      addToast(error instanceof Error ? error.message : 'Could not load conversation', 'error');
    }
  }, [setActiveMode, addToast]);

  // Delete a persisted conversation. If it is the active one, start fresh.
  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      await api.deleteChatSession(sessionId);
      setChatSessions((prev: ChatSessionSummary[]) => prev.filter((s: ChatSessionSummary) => s.id !== sessionId));
      if (currentSessionId === sessionId) {
        setMessages([]);
        setAllCitations([]);
        setCurrentSessionId(null);
      }
    } catch (error: unknown) {
      logger.error('Failed to delete chat session:', error);
      addToast(error instanceof Error ? error.message : 'Could not delete conversation', 'error');
    }
  }, [currentSessionId, addToast]);

  // Clear session (start a new conversation — the server thread is kept in History)
  // Download the conversation as Word / PDF / Markdown — strategy briefs and
  // authority maps are flattened to text; citations travel as sources.
  const handleExportConversation = useCallback(async (format: ConversationExportFormat) => {
    if (exportingConversation) return;
    const firstQuestion = messages.find((m) => m.type === 'user')?.content;
    const title = conversationTitle('Matter Strategy', firstQuestion);
    setExportingConversation(true);
    try {
      await downloadConversation(title, messages.map(researchMessageToExport), format);
    } finally {
      setExportingConversation(false);
    }
  }, [messages, exportingConversation]);

  const handleClearSession = useCallback(() => {
    setMessages([]);
    setAllCitations([]);
    setCurrentSessionId(null);
    setSessionStats({ queries: 0, citations: 0, approved: 0, rejected: 0, pending: 0 });
    setInputValue('');
  }, []);

  // Batch citation actions
  const handleBatchApprove = useCallback(() => {
    setAllCitations((prev: Citation[]) => prev.map((c: Citation) => c.status === 'pending' ? {...c, status: 'approved' as const, reviewedAt: new Date()} : c));
    setMessages((prev: ChatMessage[]) => prev.map((msg: ChatMessage) => ({
      ...msg,
      citations: msg.citations?.map((c: Citation) => c.status === 'pending' ? {...c, status: 'approved' as const} : c)
    })));
    setSessionStats((prev: SessionStats) => ({
      ...prev,
      approved: prev.approved + prev.pending,
      pending: 0,
    }));
  }, []);

  const handleBatchReject = useCallback(() => {
    setAllCitations((prev: Citation[]) => prev.map((c: Citation) => c.status === 'pending' ? {...c, status: 'rejected' as const, reviewedAt: new Date()} : c));
    setMessages((prev: ChatMessage[]) => prev.map((msg: ChatMessage) => ({
      ...msg,
      citations: msg.citations?.map((c: Citation) => c.status === 'pending' ? {...c, status: 'rejected' as const} : c)
    })));
    setSessionStats((prev: SessionStats) => ({
      ...prev,
      rejected: prev.rejected + prev.pending,
      pending: 0,
    }));
  }, []);

  // Computed
  const filteredCitations = useMemo(() => {
    if (citationFilter === 'all') return allCitations;
    return allCitations.filter((c: Citation) => c.status === citationFilter);
  }, [allCitations, citationFilter]);

  const citationStats = useMemo(() => ({
    total: allCitations.length,
    approved: allCitations.filter((c: Citation) => c.status === 'approved').length,
    rejected: allCitations.filter((c: Citation) => c.status === 'rejected').length,
    pending: allCitations.filter((c: Citation) => c.status === 'pending').length,
  }), [allCitations]);

  return {
    messages, setMessages,
    inputValue, setInputValue,
    isProcessing, setIsProcessing,
    processingStage, setProcessingStage,
    selectedCitation, setSelectedCitation,
    allCitations, setAllCitations,
    pendingMessageJump, jumpToMessage,
    citationFilter, setCitationFilter,
    currentSessionId,
    chatSessions, isLoadingSessions, loadChatSessions,
    loadSession, deleteSession,
    sessionStats, setSessionStats,
    mainDocFilter, setMainDocFilter,
    openDocs, openDocument, closeDocument, docAnnotations,
    hoveredCitationId, setHoveredCitationId,
    pendingDocJump, jumpToDocumentSpan,
    lastMessageRef, inputRef,
    handleSend, handleCitationUpdate,
    handleClearSession, handleBatchApprove, handleBatchReject,
    handleExportConversation, exportingConversation,
    filteredCitations, citationStats,
  };
}

export type ResearchState = ReturnType<typeof useResearchState>;
