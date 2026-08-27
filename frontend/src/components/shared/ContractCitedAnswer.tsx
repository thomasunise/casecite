import { useState } from 'react';
import type { ContractChatCitation } from '../../api/types';
import { Icon } from './Icon';
import { AiNotice } from './AiNotice';
import s from './ContractCitedAnswer.module.css';

interface ContractCitedAnswerProps {
  text: string;
  citations: ContractChatCitation[];
  /** Anchor this citation in the contract: scroll to it and flash it. */
  onCitationJump?: (index: number) => void;
}

/**
 * An assistant answer about a contract: the answer text (which may carry
 * [1]-style citation markers) plus the cited quotes rendered as clickable
 * quote blocks — the quote blocks are the highlight surface.
 */
export function ContractCitedAnswer({ text, citations, onCitationJump }: ContractCitedAnswerProps) {
  const [expanded, setExpanded] = useState<number | null>(null);

  return (
    <div className={s.wrapper}>
      <div className={s.answerText}>
        {text.split('\n').map((line, i) => (
          line.trim()
            ? <p key={i} className={s.answerLine}>{line}</p>
            : <div key={i} className={s.lineSpacer} />
        ))}
      </div>

      {citations.length > 0 && (
        <div className={s.citationsBlock}>
          <div className={s.citationsHeader}>
            <Icon name="Quote" size={13} />
            <span>Cited from the contract ({citations.length})</span>
            <span className={s.citationsHint}>Click to expand</span>
          </div>
          <div className={s.citationsList}>
            {citations.map((c, i) => (
              <button
                key={i}
                className={s.citationChip}
                onClick={() => { setExpanded(expanded === i ? null : i); onCitationJump?.(i); }}
                title="Click to view in the contract"
              >
                <span className={s.citationMarker}>[{i + 1}]</span>
                <blockquote className={expanded === i ? s.quoteExpanded : s.quote}>
                  {c.quote}
                </blockquote>
              </button>
            ))}
          </div>
        </div>
      )}
      <AiNotice />
    </div>
  );
}
