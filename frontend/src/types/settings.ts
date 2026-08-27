export interface RagSettings {
  vectorDb: string;
  indexName: string;
  embeddingModel: string;
  dimensions: number;
  chunkSize: number;
  chunkOverlap: number;
  similarityThreshold: number;
  topK: number;
  enableReranking: boolean;
  hybridSearch: boolean;
  citationVerification: boolean;
  contextCompression: boolean;
  queryExpansion: boolean;
  sourceTracking: boolean;
  llmModel: string;
  temperature: number;
  maxTokens: number;
  batchSize: number;
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

export interface SystemStats {
  totalDocuments: number;
  totalEmbeddings: number;
  isHealthy: boolean;
}
