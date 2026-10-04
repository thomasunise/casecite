import React from 'react';
import { Icon } from './Icon';
import type { JudgeIntelProfile, JudgeEducation, JudgePosition, DocketEntry } from '../../types';
import { safeHttpUrl } from './safeUrl';

interface OpinionsByCourtItem {
  court: string;
  count: number;
}

interface OpinionsByYearItem {
  year: number;
  count: number;
}

interface DocketsByTypeItem {
  nature_of_suit?: string;
  count: number;
}

interface JudgeProfileTabProps {
  s: Record<string, string>;
  judgeIntelProfile: JudgeIntelProfile;
}

function JudgeProfileTab({
  s,
  judgeIntelProfile,
}: JudgeProfileTabProps) {
  const recentDockets = (judgeIntelProfile.recent_dockets || []) as DocketEntry[];
  return (
    <div className={s.judgeProfileContent}>
      {/* Biography (Wikipedia) */}
      {judgeIntelProfile.wikipedia_summary && (
        <div className={s.judgeProfileSection}>
          <h3 className={s.judgeProfileSectionTitle}>Biography</h3>
          <p className={s.profileSummaryText}>{judgeIntelProfile.wikipedia_summary}</p>
        </div>
      )}

      {/* Career */}
      {(judgeIntelProfile.positions?.length ?? 0) > 0 && (
        <div className={s.judgeProfileSection}>
          <h3 className={s.judgeProfileSectionTitle}>Career</h3>
          {judgeIntelProfile.positions!.map((pos: JudgePosition, i: number) => (
            <div key={i} className={s.judgeProfileItem}>
              <strong>{pos.position_type}</strong> — {pos.court_name}
              {pos.appointer && <div className={s.judgeProfileItemMeta}>Appointed by: {pos.appointer}</div>}
              {pos.date_start && <div className={s.judgeProfileItemMeta}>{pos.date_start} — {pos.date_termination || 'Present'}{pos.termination_reason ? ` (${pos.termination_reason})` : ''}</div>}
            </div>
          ))}
        </div>
      )}

      {/* Education */}
      {(judgeIntelProfile.education?.length ?? 0) > 0 && (
        <div className={s.judgeProfileSection}>
          <h3 className={s.judgeProfileSectionTitle}>Education</h3>
          {judgeIntelProfile.education!.map((edu: JudgeEducation, i: number) => (
            <div key={i} className={s.judgeProfileItem}>
              <strong>{edu.school_name}</strong>
              {edu.degree && <span> — {edu.degree}</span>}
              {edu.degree_year && <span> ({edu.degree_year})</span>}
              {edu.school_type && <span className={s.judgeProfileItemMeta}> {edu.school_type}</span>}
            </div>
          ))}
        </div>
      )}

      {/* Case Mix */}
      {(judgeIntelProfile.dockets_by_type?.length ?? 0) > 0 && (
        <div className={s.judgeProfileSection}>
          <h3 className={s.judgeProfileSectionTitle}>Case Mix</h3>
          <div className={s.mixBars}>
            {(() => {
              const dockets = judgeIntelProfile.dockets_by_type!;
              const total = dockets.reduce((sum: number, d: DocketsByTypeItem) => sum + d.count, 0);
              const maxCount = dockets[0]?.count || 1;
              return dockets.slice(0, 10).map((d: DocketsByTypeItem, i: number) => (
                <div key={i} className={s.mixBarRow}>
                  <span className={s.mixBarLabel} title={d.nature_of_suit}>{d.nature_of_suit || 'Unknown'}</span>
                  <div className={s.mixBarTrack}>
                    <div className={s.mixBarFill} style={{ '--bar-width': `${(d.count / maxCount) * 100}%` } as React.CSSProperties} />
                  </div>
                  <span className={`${s.mixBarCount} mono`}>{Math.round((d.count / total) * 100)}%</span>
                </div>
              ));
            })()}
          </div>
        </div>
      )}

      {/* Opinions by Court */}
      {(judgeIntelProfile.opinions_by_court?.length ?? 0) > 0 && (
        <div className={s.judgeProfileSection}>
          <h3 className={s.judgeProfileSectionTitle}>Opinions by Court</h3>
          <div className={s.mixBars}>
            {(() => {
              const courts = judgeIntelProfile.opinions_by_court!.slice(0, 10);
              const maxCount = Math.max(...courts.map((c: OpinionsByCourtItem) => c.count));
              return courts.map((c: OpinionsByCourtItem, i: number) => (
                <div key={i} className={s.mixBarRow}>
                  <span className={s.mixBarLabel} title={c.court}>{c.court || 'Unknown'}</span>
                  <div className={s.mixBarTrack}>
                    <div className={s.mixBarFill} style={{ '--bar-width': `${(c.count / maxCount) * 100}%` } as React.CSSProperties} />
                  </div>
                  <span className={`${s.mixBarCount} mono`}>{c.count.toLocaleString()}</span>
                </div>
              ));
            })()}
          </div>
        </div>
      )}

      {/* Recent assigned cases (dockets) */}
      {recentDockets.length > 0 && (
        <div className={s.judgeProfileSection}>
          <h3 className={s.judgeProfileSectionTitle}>Recent Assigned Cases</h3>
          {recentDockets.slice(0, 10).map((d, i) => (
            <div key={i} className={s.judgeProfileItem}>
              <div className={s.judgeProfileItemRow}>
                <strong>{d.case_name}</strong>
                {d.url ? (
                  <a href={safeHttpUrl(d.url) ?? undefined} target="_blank" rel="noopener noreferrer" className={s.judgeProfileItemLink} title="View docket on CourtListener">
                    <Icon name="ExternalLink" size={12} />
                  </a>
                ) : null}
              </div>
              <div className={s.judgeProfileItemMeta}>
                {[d.docket_number, d.court, d.date_filed ? `Filed ${d.date_filed}` : null, d.nature_of_suit].filter(Boolean).join(' • ')}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Opinions by Year - Bar Chart */}
      {(judgeIntelProfile.opinions_by_year?.length ?? 0) > 0 && (
        <div className={s.judgeProfileSection}>
          <h3 className={s.judgeProfileSectionTitle}>Activity by Year</h3>
          <div className={s.yearBarContainer}>
            {(() => {
              const years = judgeIntelProfile.opinions_by_year!.slice(-20);
              const maxCount = Math.max(...years.map((y: OpinionsByYearItem) => y.count));
              return years.map((y: OpinionsByYearItem, i: number) => (
                <div key={i} className={s.yearBar} title={`${y.year}: ${y.count} opinions`}>
                  <div
                    className={`${s.yearBarFill} ${y.count > 0 ? s.yearBarFillActive : ''}`}
                    style={{ '--bar-height': `${maxCount > 0 ? (y.count / maxCount) * 64 : 0}px` } as React.CSSProperties}
                  />
                  <span className={s.yearBarLabel}>
                    {String(y.year).slice(-2)}
                  </span>
                </div>
              ));
            })()}
          </div>
        </div>
      )}
    </div>
  );
}

export { JudgeProfileTab };
export default JudgeProfileTab;
