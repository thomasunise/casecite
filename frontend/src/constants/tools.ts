// Legal lookup tools (CourtListener-backed). Shared by the left-sidebar
// launchers and the center ToolsView. Selecting a tool opens it in the main
// content area (not the right panel).
export const LEGAL_TOOLS = [
  { id: 'case-lookup', name: 'Case Lookup', icon: 'Search', desc: 'Find by citation or name', placeholder: 'e.g., 347 U.S. 483 or Miranda v. Arizona' },
  { id: 'validate-citation', name: 'Citation Check', icon: 'ShieldCheck', desc: 'Scan citing opinions for negative treatment', placeholder: 'e.g., 410 U.S. 113' },
  { id: 'judge-analyzer', name: 'Judge Intel', icon: 'Gavel', desc: 'Profiles, metrics & strategy', placeholder: 'e.g., Sotomayor' },
  { id: 'precedents', name: 'Precedents', icon: 'Scale', desc: 'Most-cited cases on topic', placeholder: 'e.g., qualified immunity' },
  { id: 'dockets', name: 'Dockets', icon: 'FolderOpen', desc: 'Court filings & cases', placeholder: 'Search terms or party' },
  { id: 'oral-arguments', name: 'Oral Arguments', icon: 'Mic', desc: 'Audio recordings', placeholder: 'Case or topic' },
  { id: 'trends', name: 'Trends', icon: 'TrendingUp', desc: 'Case law over time', placeholder: 'Topic to analyze' },
] as const;

export type LegalTool = (typeof LEGAL_TOOLS)[number];

// Tools whose results are list/data oriented and benefit from a "chat about
// these results" box in the center view. Case Lookup and Judge Analysis hand
// off to CaseView / JudgeIntelView (which carry their own chat), so they are
// intentionally excluded here.
export const TOOLS_WITH_RESULT_CHAT: readonly string[] = [
  'validate-citation',
  'precedents',
  'dockets',
  'oral-arguments',
  'trends',
];
