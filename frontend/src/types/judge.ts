export interface JudgeEducation {
  school_name: string;
  degree?: string;
  degree_year?: string;
  school_type?: string;
  [key: string]: unknown;
}

export interface JudgePosition {
  position_type?: string;
  court_name: string;
  appointer?: string;
  date_start?: string;
  date_termination?: string;
  termination_reason?: string;
  [key: string]: unknown;
}

export interface OpinionEntry {
  case_name: string;
  citation?: string;
  court?: string;
  date_filed?: string;
  citation_count?: number;
  [key: string]: unknown;
}

export interface OpinionStats {
  total_opinions?: number;
  total_citations?: number;
  first_opinion?: string;
  last_opinion?: string;
  [key: string]: unknown;
}

export interface DocketStats {
  total_dockets: number;
  first_docket?: string;
  last_docket?: string;
  [key: string]: unknown;
}

export interface DocketEntry {
  case_name: string;
  docket_number?: string;
  court?: string;
  date_filed?: string;
  nature_of_suit?: string;
  [key: string]: unknown;
}

export interface JudgeIntelProfile {
  id: string;
  name: string;
  date_of_birth?: string;
  place_of_birth_city?: string;
  place_of_birth_state?: string;
  political_affiliation?: string;
  gender?: string;
  education?: JudgeEducation[];
  positions?: JudgePosition[];
  most_cited_opinions?: OpinionEntry[];
  opinions_by_year?: Array<{ year: number; count: number }>;
  opinions_by_court?: Array<{ court: string; count: number }>;
  opinion_stats?: OpinionStats;
  docket_stats?: DocketStats;
  recent_dockets?: DocketEntry[];
  dockets_by_type?: Array<{ nature_of_suit: string; count: number }>;
  wikipedia_url?: string;
  wikipedia_summary?: string;
  wikipedia_early_life?: string;
  wikipedia_education?: string;
  wikipedia_career?: string;
  wikipedia_judicial_service?: string;
  wikipedia_notable_cases?: string;
  wikipedia_personal_life?: string;
  error?: string;
  [key: string]: unknown;
}

export interface OpinionSummary {
  id: string;
  case_name: string;
  date: string;
  court: string;
  summary?: string;
  url?: string;
  full_text?: string;
  relevance?: number;
  date_filed?: string;
  citation?: string;
  citation_count?: number;
  snippet?: string;
  [key: string]: unknown;
}

export interface OpinionListResponse {
  opinions: OpinionSummary[];
  total?: number;
  [key: string]: unknown;
}

export interface JudgeStats {
  overview?: {
    total_opinions?: number;
    total_citations?: number;
    avg_citations_per_opinion?: number;
    avg_opinion_length?: number;
  };
  by_year?: Array<{ year: number; opinions: number }>;
  by_day_of_week?: Array<{ day_of_week?: string; opinions: number }>;
  by_court?: Array<{ court?: string; opinions: number }>;
  citation_distribution?: Array<{ citation_range: string; count: number }>;
  [key: string]: unknown;
}

export interface JudgeMetricValue {
  data_quality?: string;
  [key: string]: unknown;
}

export interface JudgeMetrics {
  judge_id?: number;
  judge_name?: string;
  computed_at?: string | null;
  metrics: Record<string, JudgeMetricValue>;
  methodology?: Record<string, { description?: string; calculation?: string; limitations?: string; interpretation?: string }>;
  summary?: { strengths?: string[]; cautions?: string[]; data_quality_overall?: string; recommendation?: string };
  error?: string;
}

export interface JudgeSearchResult {
  id: string;
  name: string;
  name_full?: string;
  court?: string;
  position?: string;
  appointed_by?: string;
  match_score?: number;
  [key: string]: unknown;
}

export interface JudgeSearchResponse {
  results?: JudgeSearchResult[];
  judges?: JudgeSearchResult[];
  count?: number;
  total_available?: number;
  error?: string;
  [key: string]: unknown;
}

export interface JudgeMessage {
  id: number;
  type: 'user' | 'assistant';
  content: string;
}
