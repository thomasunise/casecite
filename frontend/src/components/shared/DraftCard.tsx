import type { ContractDraft } from '../../api/types';
import { Icon } from './Icon';
import { AiNotice } from './AiNotice';
import s from './DraftCard.module.css';

interface DraftCardProps {
  draft: ContractDraft;
  exporting: boolean;
  onDownload: (title: string, text: string) => void;
}

/**
 * A drafted document rendered inside an assistant chat message: title
 * heading, the drafted text in a scrollable block that preserves line
 * breaks, and a Word download button.
 */
export function DraftCard({ draft, exporting, onDownload }: DraftCardProps) {
  return (
    <div className={s.wrapper}>
      <div className={s.header}>
        <div className={s.headText}>
          <p className={s.overline}>Draft</p>
          <h2 className={s.title}>{draft.title}</h2>
        </div>
        <button
          className={s.downloadBtn}
          onClick={() => onDownload(draft.title, draft.text)}
          disabled={exporting}
        >
          {exporting
            ? <Icon name="Loader2" size={13} className={s.spin} />
            : <Icon name="Download" size={13} />}
          Download .docx
        </button>
      </div>
      <pre className={s.draftText}>{draft.text}</pre>
      <AiNotice />
    </div>
  );
}
