import { Icon } from './Icon';
import { AiNotice } from './AiNotice';
import type { ContractRedlineEdit } from '../../api/types';
import s from './RedlineSummary.module.css';

interface RedlineSummaryProps {
  edits: ContractRedlineEdit[];
  /** The instructions/playbook the redline was drafted on, if any. */
  basis?: string;
  exporting: boolean;
  onExport: () => void;
  onViewInDocument: () => void;
}

/* Compact chat receipt for a redline run — the actual redlining happens
   inline in the document above, so the chat only reports the outcome. */
export function RedlineSummary({ edits, basis, exporting, onExport, onViewInDocument }: RedlineSummaryProps) {
  return (
    <div className={s.card}>
      <div className={s.headline}>
        <Icon name="FilePen" size={15} className={s.icon} />
        <span>
          {edits.length} redline{edits.length === 1 ? '' : 's'} proposed
        </span>
      </div>
      <p className={s.hint}>
        They're marked in the contract above — click any red clause or use the rail
        to accept, reject, or preview the proposed language.
      </p>
      {basis ? (
        <p className={s.basis}>
          <Icon name="Compass" size={12} /> Drafted per your instructions:
          {' '}&ldquo;{basis.length > 160 ? basis.slice(0, 160) + '…' : basis}&rdquo;
        </p>
      ) : (
        <p className={s.basis}>
          <Icon name="Compass" size={12} /> Reviewed against market-standard positions.
          Tell me who you represent, or set your firm playbook in Settings → Prompts,
          for redlines drafted from your side.
        </p>
      )}
      <div className={s.actions}>
        <button className={s.viewBtn} onClick={onViewInDocument}>
          <Icon name="ArrowUp" size={13} /> Work the redlines
        </button>
        <button className={s.exportBtn} onClick={onExport} disabled={exporting}>
          {exporting
            ? <Icon name="Loader2" size={13} className={s.spin} />
            : <Icon name="Download" size={13} />}
          Export tracked changes (.docx)
        </button>
      </div>
      <AiNotice />
    </div>
  );
}
