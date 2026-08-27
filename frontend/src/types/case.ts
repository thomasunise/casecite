export interface CaseInfo {
  id: string;
  name: string;
  case_name?: string;
  case_number?: string;
  court?: string;
  date_filed?: string;
  status?: string;
  parties?: string[];
  summary?: string;
  docket_url?: string;
  source?: string;
  syllabus?: string;
  opinion_text?: string;
  plain_text?: string;
  judges?: string;
  citations?: Array<string | Record<string, unknown>>;
  times_cited?: number;
  citation_count?: number;
  error?: string;
  [key: string]: unknown;
}

export interface CaseMessage {
  id: number;
  type: 'user' | 'assistant';
  content: string;
}

export interface CaseComparisonPassage {
  source: string;
  text: string;
}

export interface CaseComparisonData {
  case_name: string;
  case_citation?: string;
  strength_rating: string;
  documents_searched: number;
  confidence_score: number;
  key_holdings?: string[];
  applicability_analysis?: string;
  supporting_points?: string[];
  distinguishing_factors?: string[];
  relevant_doc_passages?: CaseComparisonPassage[];
  recommendation?: string;
}
