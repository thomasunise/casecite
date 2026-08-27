import { useState, useEffect, useContext, useId } from 'react';
import { Icon } from '../shared/Icon';
import { ModalShell } from '../shared/ModalShell';
import { safeHttpUrl } from '../shared/safeUrl';
import { OpinionAnchorView } from '../shared/OpinionAnchorView';
import { useUIStore } from '../../stores/uiStore';
import { useCaseViewStore } from '../../stores/caseViewStore';
import ResearchContext from '../../contexts/ResearchContext';
import { appNavigate } from '../../utils/router';
import { copyToClipboard } from '../../utils/copyToClipboard';
import type { Citation, ReasoningStep } from '../../types';
import s from './CitationModal.module.css';

interface CitationModalProps {
  isOpen: boolean;
  onClose: () => void;
  citation: Citation | null;
  onUpdateStatus: (id: string, status: string, notes: string) => void;
}

export const CitationModal = ({ isOpen, onClose, citation, onUpdateStatus: _onUpdateStatus }: CitationModalProps) => {
  // Optional: the modal renders anywhere; tracing needs the research state.
  const jumpToDocumentSpan = useContext(ResearchContext)?.jumpToDocumentSpan;
  const [notes, setNotes] = useState(citation?.notes || '');
  const [_status, setStatus] = useState(citation?.status || 'pending');

  useEffect(() => {
    if (citation) {
      setNotes(citation.notes || '');
      setStatus(citation.status || 'pending');
    }
  }, [citation]);

  const id = useId();

  if (!isOpen || !citation) return null;

  // Backend-supplied link: only an http(s) URL becomes an anchor.
  const courtListenerUrl = citation.notes?.includes('CourtListener URL:')
    ? safeHttpUrl(citation.notes.replace('CourtListener URL: ', ''))
    : null;

  return (
    <ModalShell onClose={onClose} overlayClassName={s.modalOverlay} className={s.modalContainer} labelledBy={`${id}-title`}>
        <div className={s.modalHeader}>
          <div className={s.modalHeaderLeft}>
            <div>
              <p className={s.modalTitleOverline}>Source verification</p>
              <h2 id={`${id}-title`} className={s.modalTitle}>Citation Analysis</h2>
            </div>
          </div>
          <div className={s.modalHeaderRight}>
            <button className={s.modalClose} onClick={onClose} aria-label="Close"><Icon name="X" size={20} /></button>
          </div>
        </div>

        <div className={s.modalBody}>
          <div className={s.citationSourceCard}>
            <div className={s.citationSourceHeader}>
              <span className={s.citationSourceType}>
                {citation.type === 'case_law' ? 'Case Law · CourtListener' : 'Internal Document'}
              </span>
              {/* The ONLY quality signal is binary verification — scores and
                  ranks are retrieval telemetry, not legal judgments. */}
              {citation.verified === true && (
                <span className={s.verifiedBadge}>
                  <Icon name="ShieldCheck" size={12} /> Verified verbatim
                </span>
              )}
              {citation.verified === false && (
                <span className={s.unverifiedBadge}>
                  <Icon name="ShieldAlert" size={12} /> Unverified
                </span>
              )}
            </div>
            <h3 className={s.citationSourceTitle}>{citation.source}</h3>
            <p className={s.citationSourceRef}>{citation.reference}</p>
            {courtListenerUrl && (
              <a
                href={courtListenerUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={s.courtListenerLink}
              >
                <Icon name="ExternalLink" size={14} /> View on CourtListener
              </a>
            )}
          </div>

          <div className={s.contentPadding}>
            {citation.caseSummary && (
              <div className={s.sectionBlock}>
                <h4 className={s.sectionTitle}>Case Summary</h4>
                <div className={s.passageBox}>
                  <p>{citation.caseSummary}</p>
                </div>
              </div>
            )}

            <div className={s.sectionBlock}>
              <h4 className={s.sectionTitle}>Cited Passage</h4>
              <div className={s.passageBox}>
                <p>{citation.passage}</p>
              </div>
            </div>

            {citation.opinionId && (
              <div className={s.sectionBlock}>
                <h4 className={s.sectionTitle}>Verify in Source Opinion</h4>
                <OpinionAnchorView
                  opinionId={citation.opinionId}
                  passage={citation.passage}
                  onOpenFull={() => { useCaseViewStore.getState().loadCaseDetail(citation.opinionId as string); onClose(); }}
                />
              </div>
            )}

            {(citation.reasoning?.length ?? 0) > 0 && (
              <div className={s.sectionBlock}>
                <h4 className={s.sectionTitle}>Reasoning Chain</h4>
                <div className={s.reasoningChain}>
                  {citation.reasoning?.map((step: ReasoningStep, i: number) => (
                    <div key={i} className={s.reasoningStep}>
                      <div className={s.stepNum}>{i + 1}.</div>
                      <div className={s.stepBody}>
                        <span className={s.stepType}>{step.type}</span>
                        <p className={s.stepDesc}>{step.description}</p>
                        {step.evidence && <div className={s.stepEvidence}><Icon name="ArrowRight" size={12} /> {step.evidence}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className={s.sectionBlock}>
              <h4 className={s.sectionTitle}>Conclusion Logic</h4>
              <div className={s.logicGrid}>
                {[
                  { label: 'Query Intent', value: citation.logic?.queryIntent },
                  { label: 'Match Criteria', value: citation.logic?.matchingCriteria },
                  { label: 'Application', value: citation.logic?.application },
                ].map((item, i) => (
                  <div key={i} className={s.logicItem}>
                    <span className={s.logicLabel}>{item.label}</span>
                    <span className={s.logicValue}>{item.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className={s.sectionBlock}>
              <h4 id={`${id}-notes`} className={s.sectionTitle}>Review Notes</h4>
              <textarea
                aria-labelledby={`${id}-notes`}
                className={s.textarea}
                value={notes}
                onChange={e => setNotes(e.target.value)}
                placeholder="Add notes about this citation for the case file..."
                rows={3}
              />
            </div>
          </div>
        </div>

        <div className={s.modalFooter}>
          <div className={s.reviewActions}>
            {citation.document_id && citation.docSpanStart != null && jumpToDocumentSpan && (
              <button
                className={s.btnSecondary}
                onClick={() => {
                  // Open the cited file in the Matter Strategy viewer, scrolled
                  // to the exact verified span, highlighted — manual tracing.
                  jumpToDocumentSpan(citation.document_id!, citation.source, citation.docSpanStart!);
                  appNavigate('/research');
                  onClose();
                }}
              >
                <Icon name="FileSearch" size={16} /> Trace in document
              </button>
            )}
            <button className={s.btnSecondary} onClick={async () => {
              const citationText = `${citation.source}`;
              const ok = await copyToClipboard(citationText);
              useUIStore.getState().addToast(ok ? 'Citation copied to clipboard' : 'Failed to copy citation', ok ? 'success' : 'error');
            }}>
              <Icon name="Copy" size={16} /> Copy Citation
            </button>
            {citation.type === 'case_law' && citation.notes?.includes('CourtListener URL:') && (
              <button className={s.btnSecondary} onClick={() => {
                const url = citation.notes.replace('CourtListener URL: ', '');
                if (url.startsWith('https://www.courtlistener.com/') || url.startsWith('https://courtlistener.com/')) {
                  window.open(url, '_blank', 'noopener,noreferrer');
                }
              }}>
                <Icon name="ExternalLink" size={16} /> View on CourtListener
              </button>
            )}
          </div>
          <button className={s.btnPrimary} onClick={onClose}>
            <Icon name="X" size={16} /> Close
          </button>
        </div>
    </ModalShell>
  );
};
