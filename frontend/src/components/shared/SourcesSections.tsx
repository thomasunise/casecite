import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Icon } from './Icon';
import { SourcesList } from './SourcesList';
import { RedlinePanel } from './RedlinePanel';
import { ComparisonPanel } from './ComparisonPanel';
import { useContractsStore } from '../../stores/contractsStore';
import { groupCitationsBySource } from '../../utils';
import type { Citation } from '../../types';
import s from './SourcesSections.module.css';

interface SourcesSectionsProps {
  /** The RightPanel's CSS module, for the inner citation lists. */
  panelStyles: Record<string, string>;
  allCitations: Citation[];
  setSelectedCitation: (cite: Citation) => void;
  /** Scroll the conversation to the answer a group of sources came from. */
  onJumpToMessage?: (messageId: string) => void;
  /** Citation hovered in the chat's numbered pills — spotlit in the lists. */
  hoveredCitationId?: string | null;
}

const QUESTION_LABEL_LIMIT = 72;

/** Per-question subgroups (conversation order) for one citation type. */
function groupByQuestion(citations: Citation[]) {
  const groups: Array<{ key: string; messageId: string | null; label: string; citations: Citation[] }> = [];
  const index = new Map<string, number>();
  for (const c of citations) {
    const key = c.messageId || '_ungrouped';
    if (!index.has(key)) {
      index.set(key, groups.length);
      const label = (c.sourceQuery || '').trim();
      groups.push({
        key,
        messageId: c.messageId || null,
        label: label.length > QUESTION_LABEL_LIMIT ? `${label.slice(0, QUESTION_LABEL_LIMIT)}…` : label,
        citations: [],
      });
    }
    groups[index.get(key)!].citations.push(c);
  }
  return groups;
}

/* The global Sources surface, categorized by TYPE — Redlines, Case Law,
   Documents — one collapsible bucket each, so "hide all documents" is one
   click. Inside a bucket, citations keep their per-question subgroups
   (conversation order) with a jump-to-answer arrow on each. */
export function SourcesSections({ panelStyles, allCitations, setSelectedCitation, onJumpToMessage, hoveredCitationId }: SourcesSectionsProps) {
  const location = useLocation();
  const getActiveRedlines = useContractsStore((st) => st.getActiveRedlines);
  const contractMessages = useContractsStore((st) => st.messages);
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  const activeRedlines = location.pathname === '/contracts' ? getActiveRedlines() : null;
  const latestComparisons = (() => {
    if (location.pathname !== '/contracts') return null;
    for (let i = contractMessages.length - 1; i >= 0; i--) {
      const m = contractMessages[i];
      if (m.kind === 'comparison_set' && m.comparisonSet) return m.comparisonSet.comparisons;
      if (m.kind === 'comparison' && m.comparison) return [m.comparison];
    }
    return null;
  })();
  const caseLaw = allCitations.filter((c) => c.type === 'case_law');
  const documents = allCitations.filter((c) => c.type !== 'case_law');

  const renderTypeBody = (citations: Citation[]) => {
    const groups = groupByQuestion(citations);
    return (
      <>
        {groups.map((group) => (
          <div key={group.key} className={s.qGroup}>
            {group.label && (
              <div className={s.qHeader}>
                <span className={s.qLabel}>{group.label}</span>
                {group.messageId && onJumpToMessage && (
                  <button
                    className={s.jumpBtn}
                    onClick={() => onJumpToMessage(group.messageId!)}
                    title="Go to this answer in the conversation"
                    aria-label="Go to this answer in the conversation"
                  >
                    <Icon name="MessageSquare" size={11} />
                  </button>
                )}
              </div>
            )}
            <SourcesList
              s={panelStyles}
              allCitations={group.citations}
              setSelectedCitation={setSelectedCitation}
              showTitle={false}
              hoveredCitationId={hoveredCitationId}
            />
          </div>
        ))}
      </>
    );
  };

  const sections: Array<{ key: string; title: string; count: number; body: React.ReactNode }> = [];
  if (activeRedlines) {
    sections.push({
      key: 'redlines',
      title: 'Redlines',
      count: activeRedlines.edits.length,
      body: <RedlinePanel />,
    });
  }
  if (latestComparisons && latestComparisons.length > 0) {
    sections.push({
      key: 'comparison',
      title: 'Comparison',
      count: latestComparisons.reduce((n, c) => n + c.clauses.length, 0),
      body: <ComparisonPanel />,
    });
  }
  if (caseLaw.length > 0) {
    sections.push({
      key: 'caselaw',
      title: 'Case Law',
      count: groupCitationsBySource(caseLaw).length,
      body: renderTypeBody(caseLaw),
    });
  }
  if (documents.length > 0) {
    sections.push({
      key: 'documents',
      title: 'Documents',
      count: groupCitationsBySource(documents).length,
      body: renderTypeBody(documents),
    });
  }

  if (sections.length === 0) {
    return (
      <div className={s.empty}>
        <Icon name="FileSearch" size={24} className={s.emptyIcon} />
        <div>No sources yet</div>
        <div className={s.emptyDesc}>
          Search, review, or redline — cited material and edits land here by type.
        </div>
      </div>
    );
  }

  return (
    <div className={s.sections}>
      {sections.map((section) => {
        const isCollapsed = !!collapsedSections[section.key];
        return (
          <div key={section.key} className={s.section}>
            <button
              className={s.sectionHeader}
              onClick={() =>
                setCollapsedSections((prev) => ({ ...prev, [section.key]: !isCollapsed }))
              }
              aria-expanded={!isCollapsed}
            >
              <span className={s.sectionTitle}>
                {section.title} ({section.count})
              </span>
              <Icon name={isCollapsed ? 'ChevronDown' : 'ChevronUp'} size={13} />
            </button>
            {!isCollapsed && <div className={s.sectionBody}>{section.body}</div>}
          </div>
        );
      })}
    </div>
  );
}
