import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icon';
import type { ConversationExportFormat } from '../../api/types';
import s from './ExportMenu.module.css';

interface ExportMenuProps {
  onExport: (format: ConversationExportFormat) => void;
  busy?: boolean;
  /** Button label; defaults to "Export". */
  label?: string;
  /** Extra class for the trigger button, to match a host toolbar's buttons. */
  buttonClassName?: string;
  /** Open the menu upward (for controls near the bottom of the screen). */
  dropUp?: boolean;
}

const OPTIONS: { format: ConversationExportFormat; label: string; hint: string; icon: string }[] = [
  { format: 'docx', label: 'Word', hint: '.docx', icon: 'FileText' },
  { format: 'pdf', label: 'PDF', hint: '.pdf', icon: 'File' },
  { format: 'md', label: 'Markdown', hint: '.md', icon: 'Hash' },
];

/** Export trigger with a format menu — one look for every export in the app. */
export function ExportMenu({ onExport, busy, label = 'Export', buttonClassName, dropUp }: ExportMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className={s.root} ref={rootRef}>
      <button
        type="button"
        className={buttonClassName || s.trigger}
        onClick={() => setOpen((v) => !v)}
        disabled={busy}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Export as Word, PDF or Markdown"
      >
        {busy ? <Icon name="Loader2" size={12} className={s.spin} /> : <Icon name="Download" size={12} />}
        {label}
        <Icon name="ChevronDown" size={11} className={s.caret} />
      </button>
      {open && (
        <div className={dropUp ? s.menuUp : s.menu} role="menu">
          {OPTIONS.map((o) => (
            <button
              key={o.format}
              type="button"
              role="menuitem"
              className={s.item}
              onClick={() => { setOpen(false); onExport(o.format); }}
            >
              <Icon name={o.icon} size={13} className={s.itemIcon} />
              <span className={s.itemLabel}>{o.label}</span>
              <span className={s.itemHint}>{o.hint}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
