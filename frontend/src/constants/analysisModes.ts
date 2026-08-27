// Source-available build: focused on RAG over private documents and
// CourtListener-backed case/judge lookups. The knowledge base (documents +
// import sources) is not an analysis mode — it lives in its own Documents
// section in the sidebar and routes to /documents.
// Case Citations is no longer a separate mode: its exhaustive authority-map
// engine runs from the Matter Strategy chat ("give me all the case law for
// this file/folder"). The /case-citations route still serves the annotated
// document view.
export const ANALYSIS_MODES = [
  { id: 'research', title: 'Matter Strategy', icon: 'Lightbulb', desc: 'Your files, chat, strategy & verified case law' },
  { id: 'contracts', title: 'Contracts', icon: 'FileText', desc: 'Review, redline & compare contracts' },
  { id: 'drafting', title: 'Drafting', icon: 'PenLine', desc: 'Draft contracts, letters & documents' },
] as const;
