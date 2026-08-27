// ==================== Branding Types ====================

export interface BrandingConfig {
  firm_name: string;
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  favicon_url: string | null;
  custom_css: string | null;
  updated_at: string | null;
}

// ==================== API Response Types ====================

export interface AuthResponse {
  access_token: string;
  refresh_token?: string;
  user: UserInfo;
  /** Present when login requires a second factor instead of returning tokens. */
  mfa_required?: boolean;
  mfa_token?: string;
}

export interface MfaStatus {
  enabled: boolean;
  recovery_codes_remaining: number;
}

export interface MfaSetup {
  secret: string;
  provisioning_uri: string;
}

export interface MfaRecoveryCodes {
  recovery_codes: string[];
}

export interface UserInfo {
  id: string;
  email: string;
  roles: string[]; // backend returns a list of role strings, e.g. ["admin"]
  name?: string;
  role?: string; // legacy single-role field (optional)
}

export interface ChatResponse {
  id?: string;
  answer: string;
  content?: string;
  citations: Citation[];
  stats?: ChatStats;
  /** Persisted chat session this exchange belongs to (null if persistence failed). */
  session_id?: string | null;
  /** Set when the message routed to the exhaustive authority mapper: poll the
      job for an AuthorityMapChatResult. */
  authority_map_job?: { job_id: string; documents: { id: string; name: string }[] } | null;
  [key: string]: unknown;
}

interface Citation {
  text: string;
  source: string;
  page?: number;
  score?: number;
}

interface ChatStats {
  retrieval_time?: number;
  generation_time?: number;
  total_time?: number;
  chunks_retrieved?: number;
  docs_searched?: number;
  processing_time?: string;
  case_law_searched?: number;
  case_law_included?: number;
  [key: string]: unknown;
}

export interface ChatQueryOptions {
  includeCaseLaw?: boolean;
  caseLawLimit?: number;
  includeDocuments?: boolean;
  documentFilter?: string | null;
  topK?: number;
  similarityThreshold?: number;
  /** Persisted chat session to append this exchange to (null = start new). */
  sessionId?: string | null;
  [key: string]: unknown;
}

// ==================== Persistent Chat Session Types ====================

export interface ChatSessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatSessionListResponse {
  sessions: ChatSessionSummary[];
}

export interface ChatSessionMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Record<string, unknown>[];
  strategy: StrategyBriefResponse | null;
  stats: Record<string, unknown> | null;
  created_at: string;
}

export interface ChatSessionDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatSessionMessage[];
}

export interface RAGSettings {
  vectorDb: string;
  indexName: string;
  topK: number;
  similarityThreshold: number;
  chunkSize: number;
  chunkOverlap: number;
  embeddingModel: string;
  dimensions: number;
  batchSize?: number;
  llmModel?: string;
  temperature?: number;
  maxTokens?: number;
  enableReranking?: boolean;
  hybridSearch?: boolean;
  citationVerification?: boolean;
  contextCompression?: boolean;
  queryExpansion?: boolean;
  sourceTracking?: boolean;
  contract_playbook?: string | null;
  practice_area?: string | null;
  practice_profile?: string | null;
  custom_system_prompt?: string | null;
  custom_grounding_rules?: string | null;
  custom_factual_prompt?: string | null;
  custom_research_prompt?: string | null;
  custom_case_prompt?: string | null;
  custom_document_prompt?: string | null;
  custom_compliance_prompt?: string | null;
  custom_strategy_prompt?: string | null;
  [key: string]: unknown;
}

export interface DocumentInfo {
  id: string;
  name: string;
  size: number;
  status: string;
  [key: string]: unknown;
}

export interface DocumentTree {
  tree: Record<string, unknown>[];
  total_documents: number;
  [key: string]: unknown;
}

export interface DocumentContent {
  document_id: string;
  text: string;
  filename: string;
}

export interface ConnectorAuthUrl {
  url: string;
  auth_url?: string;
  connected?: boolean;
  [key: string]: unknown;
}

export interface ConnectorStatusResponse {
  connected: boolean;
  docs_indexed?: number;
  [key: string]: unknown;
}

export interface SyncStartResult {
  sync_id: string;
  status: string;
}

export interface SyncStatusResult {
  status: string;
  progress?: number;
  result?: unknown;
  error?: string;
  [key: string]: unknown;
}

export interface ConnectorDataResponse {
  connectors: Array<{
    id: string;
    connected?: boolean;
    configured?: boolean;
    docs_indexed?: number;
  }>;
  [key: string]: unknown;
}

export interface ImportResponse {
  imported: number;
  failed: number;
  message?: string;
  [key: string]: unknown;
}

export interface PickerConfig {
  provider?: string;
  token?: string;
  clientId?: string;
  appKey?: string;
  google_enabled: boolean;
  microsoft_enabled: boolean;
  box_enabled?: boolean;
  dropbox_enabled?: boolean;
  google_client_id?: string;
  google_api_key?: string;
  google_app_id?: string;
  microsoft_client_id?: string;
  microsoft_tenant_id?: string;
  dropbox_app_key?: string;
  [key: string]: unknown;
}

export interface BoxPickerToken {
  access_token: string;
  expires_in: number;
}

export interface MessageResponse {
  message: string;
  [key: string]: unknown;
}

// ==================== Matter Strategy Types ====================

export interface StrategyBriefPoint {
  point?: string;
  step?: string;
  citation_ids: string[];
  case_refs?: string[];
}

interface StrategyBriefCitation {
  id: string;
  source: string;
  type: 'document' | 'case_law' | string;
  document_id?: string | null;
  passage?: string | null;
  confidence?: number;
  reference?: string | null;
  opinionId?: string | null;
  url?: string | null;
  /** How this authority supports the point it is attached to (case_law only). */
  explanation?: string | null;
  /** True when the passage was verified verbatim against the real opinion text. */
  verified?: boolean;
}

export interface StrategyBriefResponse {
  question: string;
  scope: {
    folder_path?: string | null;
    documents_considered: number;
    documents_total: number;
  };
  position: string;
  strengths: StrategyBriefPoint[];
  weaknesses: StrategyBriefPoint[];
  next_steps: StrategyBriefPoint[];
  citations: StrategyBriefCitation[];
  /** Outcome of the case-law support stage — null when case law wasn't requested. */
  case_law?: {
    requested: boolean;
    points_searched: number;
    /** Opinions whose full text was actually retrieved and judged. */
    opinions_read: number;
    attached: number;
    /** Candidates dropped because no usable opinion text could be retrieved. */
    unreadable?: number;
    /** Opinions read in full and judged not to support any proposition. */
    unsupportive?: number;
    /** Opinions the judge endorsed but whose quote never verified verbatim. */
    quote_unverified?: number;
    /** Candidates dropped by an upstream error while judging. */
    errors?: number;
    /** Points whose CourtListener search itself failed. */
    searches_failed?: number;
    /** The concrete failure (e.g. "HTTPStatusError: 429 …") when searches failed. */
    search_error?: string | null;
    /** True when the stage hit its time budget before finishing every point. */
    timed_out?: boolean;
  } | null;
}

// ==================== Case Comparison Response Types ====================

interface CaseComparisonResponse {
  case_name: string;
  case_citation?: string;
  strength_rating: string;
  documents_searched: number;
  confidence_score: number;
  key_holdings?: string[];
  applicability_analysis?: string;
  supporting_points?: string[];
  distinguishing_factors?: string[];
  relevant_doc_passages?: Array<{ source: string; text: string }>;
  recommendation?: string;
  [key: string]: unknown;
}

// ==================== Document List Response Types ====================

interface RagDocumentItem {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  source: string;
  source_id?: string | null;
  status: 'pending' | 'processing' | 'indexed' | 'failed';
  chunk_count: number;
  created_at: string;
  indexed_at?: string | null;
  metadata?: Record<string, unknown>;
  folder_path?: string | null;
}

export interface DocumentListResponse {
  documents: RagDocumentItem[];
  total?: number;
  [key: string]: unknown;
}

// ==================== Admin Integrations Types ====================

export interface CourtListenerStatus {
  configured: boolean;
  source: 'instance' | 'env' | 'none' | string;
  masked: string | null;
}

/** Per-provider file-picker credentials status (instance DB beats .env). */
export interface ConnectorCredentialStatus {
  provider: string;
  label: string;
  configured: boolean;
  source: 'instance' | 'env' | 'none' | string;
  fields: string[];
  masked: Record<string, string | null>;
}

export interface LocalLlmStatus {
  configured: boolean;
  base_url: string | null;
  chat_model: string | null;
  utility_model: string | null;
}

export interface LocalLlmConfig {
  baseUrl: string;
  chatModel: string;
  utilityModel?: string | null;
}

// ==================== Admin User Management Types ====================

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  roles: string[];
  is_active: boolean;
  created_at?: string | null;
  last_login?: string | null;
}

export interface InviteUserResult {
  user: AdminUser;
  temporary_password: string;
}

interface PermissionInfo {
  key: string;
  label: string;
  description: string;
  group: string;
}

export interface RolePermissionsMatrix {
  permissions: PermissionInfo[];
  roles: string[];
  defaults: Record<string, string[]>;
  assigned: Record<string, string[]>;
  customized: string[];
  locked: Record<string, string[]>;
}

// ==================== Universal History (workspace sessions) ====================

export interface WorkspaceSessionSummary {
  id: string;
  surface: string;
  title: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkspaceSessionDetail extends WorkspaceSessionSummary {
  payload: Record<string, unknown>;
}

// ==================== API Client Interface ====================

export interface RequestOptions extends RequestInit {
  headers?: Record<string, string>;
  timeout?: number;
  _retried?: boolean;
}

interface AuthorityMappingReasoningStep {
  type?: string | null;
  description?: string | null;
  evidence?: string | null;
}

interface AuthorityMappingReasoning {
  steps?: AuthorityMappingReasoningStep[] | null;
  application?: string | null;
}

export interface AuthorityMapping {
  id?: number;
  proposition: string;
  doc_quote: string | null;
  doc_span_start: number | null;
  doc_span_end: number | null;
  source: 'courtlistener' | string;
  case_name: string | null;
  citation: string | null;
  source_ref: string | null;
  source_url: string | null;
  support_quote: string | null;
  source_span_start: number | null;
  source_span_end: number | null;
  verified: boolean;
  relevance: number;
  note: string | null;
  reasoning?: AuthorityMappingReasoning | null;
}

export interface AuthorityMapResult {
  run_id: string;
  document_name: string | null;
  jurisdiction: string | null;
  summary: {
    propositions?: number;
    authorities?: number;
    verified?: number;
    courtlistener?: number;
  };
  mappings: AuthorityMapping[];
}

export interface AuthorityMapJob {
  job_id: string;
  status: string; // pending | processing | completed | failed | cancelled
  result?: AuthorityMapResult | null;
  error?: string | null;
}

/** Result of a chat-triggered authority map across one or more scoped files. */
export interface AuthorityMapChatResult {
  files: (AuthorityMapResult & { document_id?: string | null })[];
  totals: { files: number; propositions: number; authorities: number; verified: number };
}

export interface AuthorityMapChatJob {
  job_id: string;
  status: string; // pending | processing | completed | failed | cancelled
  result?: AuthorityMapChatResult | null;
  error?: string | null;
}

export interface AuthorityMapPayload {
  documentText: string;
  documentName?: string | null;
  jurisdiction?: string | null;
}

// ==================== Contract Analysis Types ====================

export interface ContractKeyTerm {
  value: string;
  quote: string | null;
  span_start: number | null;
  span_end: number | null;
  verified: boolean;
}

type ContractIssueGrounding = 'span' | 'absence' | 'unverified';

export interface ContractIssue {
  ref: string;
  title: string;
  status: string;
  severity: string; // critical | major | minor | informational
  why: string;
  suggested_language?: string | null;
  span_start?: number | null;
  span_end?: number | null;
  matched_text?: string | null;
  clause_slug?: string | null;
  grounding: ContractIssueGrounding;
}

interface ContractParty {
  canonical_name: string;
  role: string | null;
  aliases: string[];
  confidence: number;
}

export interface ContractObligation {
  subject_party: string | null;
  modal: string;
  action: string;
  object_text: string | null;
  category: string | null;
  // Present on live analyze results; stored analyses return conditions instead.
  deadlines?: string[];
  conditions?: string[];
  matched_text: string;
  span_start: number | null;
  span_end: number | null;
}

export interface ContractDeadlineItem {
  kind: string; // absolute | relative_offset | period | recurring | conditional
  description: string;
  anchor: string | null;
  offset_days: number | null;
  period_days: number | null;
  resolved_date: string | null;
  matched_text: string | null;
}

interface ContractDefinedTerm {
  term: string;
  definition_text: string | null;
  defined: boolean;
  usage_count: number;
  used_but_undefined: boolean;
  defined_but_unused: boolean;
  circular_reference: boolean;
}

interface ContractAnalysisSummary {
  parties?: number;
  obligations?: number;
  deadlines?: number;
  [k: string]: unknown;
}

export interface ContractAnalysisResult {
  analysis_id: string;
  contract_type: string; // nda | msa | saas | employment | license | sow | other
  representing?: string | null;
  posture?: string | null;
  jurisdiction?: string | null;
  executive_summary?: string | null;
  key_terms: Record<string, ContractKeyTerm>;
  issues: ContractIssue[];
  parties: ContractParty[];
  obligations: ContractObligation[];
  deadlines: ContractDeadlineItem[];
  defined_terms?: ContractDefinedTerm[];
  summary: ContractAnalysisSummary;
}

/** One proposed tracked-changes edit inside a redline result. */
export interface ContractRedlineEdit {
  /** Where this proposal came from — the rule/standard that flagged it. */
  source?: string;
  ref: string;
  kind: 'replace' | 'insert';
  span_start: number;
  span_end: number;
  original_text: string;
  proposed_text: string;
  rationale: string;
  severity: string; // critical | major | minor | informational
  title: string;
}

/** Redline job result — a full analysis plus the proposed edits. */
interface ContractRedlineResult extends ContractAnalysisResult {
  kind: 'redlines';
  redlines: ContractRedlineEdit[];
}

/** Draft job result — a freshly drafted (or revised) document. */
export interface ContractDraft {
  kind: 'draft';
  /** Empty on a scoped revision: the workspace keeps its existing title. */
  title: string;
  text: string;
  /** Long drafts only: each section as drafted, before the reconcile pass. */
  sections?: Array<{ number: number; title: string; text: string }>;
  /** Long drafts only: what the reconcile pass changed (or why it was skipped). */
  reconcile_notes?: string[];
  /** "full" when every section read the whole reference bundle, "excerpts" when it had to be focused per section. */
  references_mode?: 'full' | 'excerpts' | 'none';
  /** Revisions only: which sections were rewritten, or "all". */
  revised_sections?: number[] | 'all';
}

/** One planned section of a long draft. The user can edit every field. */
export interface DraftPlanSection {
  number: number;
  title: string;
  brief: string;
  /** What this section must leave to other sections — the overlap guard. */
  exclude: string;
  target_words: number;
}

/** The shared plan every section of a long draft is written against. */
export interface DraftPlan {
  title: string;
  document_type: string;
  sections: DraftPlanSection[];
  definitions: string;
  style_guide: string;
  target_words: number;
  references_mode?: 'full' | 'excerpts' | 'none';
}

/** Plan job result — reviewed and approved before any section is written. */
interface ContractDraftPlan {
  kind: 'draft_plan';
  plan: DraftPlan;
  target_pages: number;
}

/** 202 shape shared by the long-draft endpoints. */
export interface ContractJobStarted {
  type: string;
  job_id: string;
  poll_url?: string;
}

type ContractClauseCompareStatus = 'changed' | 'added' | 'removed' | 'unchanged';

export interface ContractComparisonClause {
  topic: string;
  status: ContractClauseCompareStatus;
  summary: string;
  quote_a: string | null;
  span_a_start: number | null;
  span_a_end: number | null;
  verified_a: boolean | null;
  quote_b: string | null;
  span_b_start: number | null;
  span_b_end: number | null;
  verified_b: boolean | null;
}

/** Compare job result — clause-by-clause diff of two contracts. */
export interface ContractComparison {
  kind: 'comparison';
  overall: string;
  label_a: string;
  label_b: string;
  clauses: ContractComparisonClause[];
  /** Indexed document ids, so the UI can open both texts side by side. */
  document_id_a?: string;
  document_id_b?: string;
  /** The user's own comparison instructions, if any. */
  focus?: string | null;
}

/** Multi-document compare (3-4 docs): baseline vs each other document. */
export interface ContractComparisonSet {
  kind: 'comparison_set';
  comparisons: ContractComparison[];
  focus?: string | null;
}

/**
 * Everything a contract job can resolve to. Plain analyses carry no `kind`
 * discriminant, so narrow with `'kind' in result` / `result.kind`.
 */
export type ContractJobResult =
  | ContractAnalysisResult
  | ContractRedlineResult
  | ContractDraft
  | ContractDraftPlan
  | ContractComparison
  | ContractComparisonSet;

export interface ContractAnalysisJob {
  job_id: string;
  status: string; // pending | processing | completed | failed | cancelled
  result?: ContractJobResult | null;
  error?: string | null;
  /** Reported by long-running pipelines while status is "processing". */
  progress?: { message: string; fraction: number | null } | null;
}

export interface ContractAnalysisListItem {
  analysis_id: string;
  document_id: string | null;
  contract_type: string | null;
  created_at: string | null;
  issues: number;
}

export interface ContractAnalyzePayload {
  documentId?: string | null;
  documentText?: string | null;
  contractType?: string | null;
  representing?: string | null;
  posture?: 'balanced' | 'strict';
}

// ==================== Contract Chat Types ====================

export interface ContractChatCitation {
  quote: string;
  span_start: number;
  span_end: number;
}

/** 202 shape — the message asked for a full review; poll the job. */
interface ContractChatAnalysisStarted {
  type: 'analysis_started';
  job_id: string;
  poll_url?: string;
}

/** 202 shape — the message asked for redlines; poll the job. */
interface ContractChatRedlineStarted {
  type: 'redline_started';
  job_id: string;
  poll_url?: string;
}

/** 202 shape — the message asked for a fresh draft; poll the job. */
interface ContractChatDraftStarted {
  type: 'draft_started';
  job_id: string;
  poll_url?: string;
}

/** 202 shape — a two-document comparison kicked off; poll the job. */
export interface ContractCompareStarted {
  type: 'compare_started';
  job_id: string;
  poll_url?: string;
}

/** 200 shape — a direct answer with grounded citations. */
interface ContractChatAnswer {
  type: 'answer';
  answer: string;
  citations: ContractChatCitation[];
}

interface ContractChatClarify {
  type: 'clarify';
  question: string;
  options: string[];
}

export type ContractChatResponse =
  | ContractChatAnalysisStarted
  | ContractChatRedlineStarted
  | ContractChatDraftStarted
  | ContractChatAnswer
  | ContractChatClarify;

// ==================== Conversation Export ====================

export type ConversationExportFormat = 'docx' | 'pdf' | 'md';

interface ConversationExportCitation {
  label: string;
  quote?: string | null;
  url?: string | null;
}

export interface ConversationExportMessage {
  role: 'user' | 'assistant';
  text: string;
  citations?: ConversationExportCitation[];
}

export interface ConversationExportPayload {
  title: string;
  format: ConversationExportFormat;
  messages: ConversationExportMessage[];
}

export interface ApiClient {
  token: string | null;

  // Token management (the refresh token is an httpOnly cookie — never in JS)
  setToken(token: string): void;
  getToken(): string | null;
  initCsrf(): Promise<void>;

  // Core request methods
  // Returns any: JSON deserialization boundary — domain modules type the return values
  request(endpoint: string, options?: RequestOptions): Promise<any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  refreshAccessToken(): Promise<boolean>;
  authFetch(url: string, options?: RequestOptions): Promise<Response>;

  // Branding
  getBranding(): Promise<BrandingConfig>;
  updateBranding(config: Partial<BrandingConfig>): Promise<BrandingConfig>;
  uploadBrandingLogo(file: File): Promise<{ status: string; logo_url: string }>;
  resetBranding(): Promise<BrandingConfig>;

  // Auth
  login(email: string, password: string): Promise<AuthResponse>;
  refreshToken(): Promise<AuthResponse | null>;
  logout(): Promise<void>;
  getCurrentUser(): Promise<UserInfo>;
  register(email: string, name: string, password: string, company: string): Promise<AuthResponse>;
  forgotPassword(email: string): Promise<MessageResponse>;

  // MFA
  getMfaStatus(): Promise<MfaStatus>;
  setupMfa(): Promise<MfaSetup>;
  enableMfa(code: string): Promise<MfaRecoveryCodes>;
  disableMfa(code: string): Promise<{ status: string }>;
  verifyMfa(mfaToken: string, code: string): Promise<AuthResponse>;
  regenerateRecoveryCodes(code: string): Promise<MfaRecoveryCodes>;

  // Chat
  query(message: string, mode: string, options?: ChatQueryOptions): Promise<ChatResponse>;

  // Chat Sessions (persistent conversations)
  listChatSessions(): Promise<ChatSessionListResponse>;
  getChatSession(sessionId: string): Promise<ChatSessionDetail>;
  deleteChatSession(sessionId: string): Promise<{ status: string; id: string }>;

  // Settings
  getSettings(): Promise<RAGSettings>;
  updateSettings(settings: Record<string, unknown>): Promise<RAGSettings>;
  getKeyStatus(): Promise<Record<string, boolean>>;
  getMaskedKeys(): Promise<Record<string, string | null>>;
  saveApiKey(keyType: string, apiKey: string): Promise<void>;
  getPromptDefaults(): Promise<Record<string, unknown>>;
  reindexDocuments(): Promise<Record<string, unknown>>;
  clearAllDocuments(): Promise<{ status: string; message?: string }>;
  getCourts(): Promise<{ courts: Array<{ id: string; name: string; jurisdiction?: string }> }>;

  // Admin Integrations (admin-only)
  getCourtListenerStatus(): Promise<CourtListenerStatus>;
  setCourtListenerToken(apiToken: string): Promise<CourtListenerStatus>;
  clearCourtListenerToken(): Promise<{ status: string }>;
  getConnectorCredentials(): Promise<{ providers: ConnectorCredentialStatus[] }>;
  setConnectorCredentials(provider: string, values: Record<string, string>): Promise<ConnectorCredentialStatus>;
  clearConnectorCredentials(provider: string): Promise<ConnectorCredentialStatus>;
  getLocalLlmStatus(): Promise<LocalLlmStatus>;
  setLocalLlm(config: LocalLlmConfig): Promise<LocalLlmStatus>;
  clearLocalLlm(): Promise<{ status: string }>;

  // Universal History (workspace sessions)
  listWorkspaceSessions(): Promise<{ sessions: WorkspaceSessionSummary[] }>;
  createWorkspaceSession(surface: string, title: string, payload: Record<string, unknown>): Promise<WorkspaceSessionSummary>;
  updateWorkspaceSession(id: string, updates: { title?: string; payload?: Record<string, unknown> }): Promise<WorkspaceSessionSummary>;
  getWorkspaceSession(id: string): Promise<WorkspaceSessionDetail>;
  deleteWorkspaceSession(id: string): Promise<{ status: string; id: string }>;

  // Admin User Management (admin-only)
  getUsers(): Promise<{ users: AdminUser[] }>;
  inviteUser(email: string, name: string, role: string): Promise<InviteUserResult>;
  updateUserRole(userId: string, role: string): Promise<AdminUser>;
  getRolePermissions(): Promise<RolePermissionsMatrix>;
  updateRolePermissions(role: string, permissions: string[]): Promise<RolePermissionsMatrix>;
  resetRolePermissions(): Promise<RolePermissionsMatrix>;

  // Documents
  /** `metadata` is ignored — the server derives filename and type from the upload. */
  uploadDocument(file: File, metadata?: Record<string, string>): Promise<DocumentInfo>;
  getDocuments(limit?: number, offset?: number): Promise<DocumentListResponse>;
  getDocumentTree(): Promise<DocumentTree>;
  getDocumentContent(documentId: string): Promise<DocumentContent>;
  deleteDocument(documentId: string): Promise<MessageResponse>;
  listFolders(): Promise<{ folders: string[] }>;
  createFolder(name: string): Promise<{ path: string; folders: string[] }>;
  deleteFolder(path: string): Promise<{ status: string; folders: string[] }>;
  moveDocument(documentId: string, folderPath: string | null): Promise<{ status: string }>;

  // Connectors
  getConnectors(): Promise<ConnectorDataResponse>;
  connectConnector(connectorId: string): Promise<ConnectorAuthUrl>;
  disconnectConnector(connectorId: string): Promise<MessageResponse>;
  syncConnector(connectorId: string, options?: Record<string, unknown>): Promise<SyncStartResult>;
  getConnectorSyncStatus(connectorId: string, syncId: string): Promise<SyncStatusResult>;
  getConnectorStatus(connectorId: string): Promise<ConnectorStatusResponse>;

  // Pickers
  getPickerConfig(): Promise<PickerConfig>;
  getBoxPickerToken(): Promise<BoxPickerToken>;
  importFromGooglePicker(files: unknown[]): Promise<ImportResponse>;
  importFromOneDrivePicker(files: unknown[]): Promise<ImportResponse>;
  importFromBoxPicker(files: unknown[]): Promise<ImportResponse>;
  importFromDropboxChooser(files: unknown[]): Promise<ImportResponse>;

  // Matter Strategy & Authority Map
  submitAuthorityMap(payload: AuthorityMapPayload): Promise<{ job_id: string }>;
  getAuthorityMapJob(jobId: string): Promise<AuthorityMapJob>;
  getChatAuthorityMapJob(jobId: string): Promise<AuthorityMapChatJob>;
  getCaseOpinion(opinionId: string): Promise<{ case_name?: string; opinion_text?: string; syllabus?: string; [k: string]: unknown }>;

  // Contract Analysis
  analyzeContract(payload: ContractAnalyzePayload): Promise<{ job_id: string; poll_url?: string }>;
  getContractJob(jobId: string): Promise<ContractAnalysisJob>;
  listContractAnalyses(): Promise<{ analyses: ContractAnalysisListItem[] }>;
  getContractAnalysis(id: string): Promise<ContractAnalysisResult>;
  exportContractAnalysis(id: string, format: 'docx' | 'md'): Promise<Blob>;
  contractChat(documentId: string | null, message: string, mode?: string, draftText?: string, referenceIds?: string[]): Promise<ContractChatResponse>;
  generatePracticeProfile(practiceArea: string): Promise<{ practice_area: string; profile: string }>;
  compareContracts(documentIds: string[], focus?: string): Promise<ContractCompareStarted>;
  exportRedlines(analysisId: string, excludeRefs: string[], overrides?: Record<string, string>): Promise<Blob>;
  exportDraft(title: string, text: string): Promise<Blob>;
  planDraft(message: string, referenceIds: string[], targetPages: number): Promise<ContractJobStarted>;
  generateDraft(plan: DraftPlan, message: string, referenceIds: string[]): Promise<ContractJobStarted>;
  /** Render a chat transcript as Word / PDF / Markdown (POST /chat/export). */
  exportConversation(payload: ConversationExportPayload): Promise<Blob>;

  // Comparison
  compareCaseToDocuments(caseId: string, caseName: string, caseCitation: string, caseText: string, documentFilter?: Record<string, unknown> | string | null): Promise<CaseComparisonResponse>;
}
