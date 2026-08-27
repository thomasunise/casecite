import { useId } from 'react';
import { Icon } from '../shared/Icon';
import { ModalShell } from '../shared/ModalShell';
import type { CaseComparisonData } from '../../types';
import s from './CaseComparisonModal.module.css';

interface CaseComparisonModalProps {
  isOpen: boolean;
  onClose: () => void;
  data: CaseComparisonData | null;
  loading: boolean;
}

export const CaseComparisonModal = ({ isOpen, onClose, data, loading }: CaseComparisonModalProps) => {
  const titleId = useId();
  if (!isOpen) return null;

  const strengthColors = {
    strong: { bg: 'var(--green-100)', color: 'var(--green-700)', icon: 'ThumbsUp' },
    moderate: { bg: 'var(--blue-100)', color: 'var(--blue-700)', icon: 'Scale' },
    weak: { bg: 'var(--amber-100)', color: 'var(--amber-700)', icon: 'AlertTriangle' },
    adverse: { bg: 'var(--red-100)', color: 'var(--red-700)', icon: 'ThumbsDown' },
    unknown: { bg: 'var(--gray-100)', color: 'var(--gray-700)', icon: 'HelpCircle' }
  };

  const strength = data?.strength_rating || 'unknown';
  const strengthStyle = strengthColors[strength as keyof typeof strengthColors] || strengthColors.unknown;

  return (
    <ModalShell onClose={onClose} overlayClassName={s.overlay} className={s.container} labelledBy={titleId}>
        {/* Header */}
        <div className={s.header}>
          <div>
            <div className={s.headerRow}>
              <div className={s.headerIconBox}>
                <Icon name="GitCompare" size={18} className={s.iconWhite} />
              </div>
              <h2 id={titleId} className={s.headerTitle}>Case Comparison</h2>
            </div>
            {data && (
              <p className={s.headerCaseName}>
                {data.case_name} {data.case_citation && `(${data.case_citation})`}
              </p>
            )}
          </div>
          <button onClick={onClose} className={s.closeBtn} aria-label="Close">
            <Icon name="X" size={20} className={s.iconGray600} />
          </button>
        </div>

        {/* Content */}
        <div className={s.content}>
          {loading ? (
            <div className={s.loadingState}>
              <div className={s.spinner} />
              <p className={s.loadingText}>Analyzing case against your documents...</p>
              <p className={s.loadingSubtext}>This may take a moment</p>
            </div>
          ) : data ? (
            <div className={s.resultContainer}>
              {/* Strength Badge */}
              <div className={s.strengthBadge} style={{ background: strengthStyle.bg }}>
                <Icon name={strengthStyle.icon} size={22} style={{ color: strengthStyle.color }} />
                <div>
                  <div className={s.strengthLabel} style={{ color: strengthStyle.color }}>
                    {strength === 'adverse' ? 'Adverse Precedent' : `${strength} Support`}
                  </div>
                  <div className={s.strengthMeta} style={{ color: strengthStyle.color }}>
                    {data.documents_searched} documents searched | {Math.round(data.confidence_score * 100)}% confidence
                  </div>
                </div>
              </div>

              {/* Key Holdings */}
              <div>
                <h3 className={s.sectionHeading}>
                  <Icon name="Gavel" size={14} className={s.inlineIcon} />
                  Key Holdings
                </h3>
                <ul className={s.holdingsList}>
                  {data.key_holdings?.map((holding: string, i: number) => (
                    <li key={i} className={s.holdingItem}>{holding}</li>
                  ))}
                </ul>
              </div>

              {/* Applicability Analysis */}
              <div>
                <h3 className={s.sectionHeading}>
                  <Icon name="Target" size={14} className={s.inlineIcon} />
                  How This Applies to Your Case
                </h3>
                <div className={s.analysisBox}>
                  {data.applicability_analysis || 'No analysis available.'}
                </div>
              </div>

              {/* Supporting Points & Distinguishing Factors */}
              <div className={s.twoColGrid}>
                <div>
                  <h3 className={s.sectionHeadingGreen}>
                    <Icon name="Plus" size={14} className={s.inlineIcon} />
                    Supporting Points
                  </h3>
                  <ul className={s.listSmall}>
                    {data.supporting_points && data.supporting_points.length > 0 ? data.supporting_points.map((point: string, i: number) => (
                      <li key={i} className={s.listItemSmall}>{point}</li>
                    )) : <li className={s.noData}>None identified</li>}
                  </ul>
                </div>
                <div>
                  <h3 className={s.sectionHeadingAmber}>
                    <Icon name="Minus" size={14} className={s.inlineIcon} />
                    Distinguishing Factors
                  </h3>
                  <ul className={s.listSmall}>
                    {data.distinguishing_factors && data.distinguishing_factors.length > 0 ? data.distinguishing_factors.map((factor: string, i: number) => (
                      <li key={i} className={s.listItemSmall}>{factor}</li>
                    )) : <li className={s.noData}>None identified</li>}
                  </ul>
                </div>
              </div>

              {/* Relevant Document Passages */}
              {data.relevant_doc_passages && data.relevant_doc_passages.length > 0 && (
                <div>
                  <h3 className={s.sectionHeading}>
                    <Icon name="FileText" size={14} className={s.inlineIcon} />
                    Relevant Passages from Your Documents
                  </h3>
                  <div className={s.passageList}>
                    {data.relevant_doc_passages.slice(0, 3).map((passage: { source: string; text: string }, i: number) => (
                      <div key={i} className={s.passageCard}>
                        <div className={s.passageSource}>{passage.source}</div>
                        <div className={s.passageText}>{passage.text}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Strategic Recommendation */}
              <div className={s.recommendationBox}>
                <h3 className={s.recommendationTitle}>
                  <Icon name="Lightbulb" size={14} className={s.inlineIcon} />
                  Strategic Recommendation
                </h3>
                <div className={s.recommendationText}>
                  {data.recommendation || 'No recommendation available.'}
                </div>
              </div>
            </div>
          ) : (
            <div className={s.emptyState}>
              No comparison data available.
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={s.footer}>
          <button onClick={onClose} className={s.closeButton}>
            Close
          </button>
        </div>
    </ModalShell>
  );
};
