import React, { useId } from 'react';
import { SHORTCUTS_LIST } from '../../hooks/useKeyboardShortcuts';
import { ModalShell } from '../shared/ModalShell';
import s from './ShortcutsHelp.module.css';

interface ShortcutsHelpProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ShortcutsHelp = ({ isOpen, onClose }: ShortcutsHelpProps) => {
  const titleId = useId();

  if (!isOpen) return null;

  const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);
  const modLabel = isMac ? '\u2318' : 'Ctrl';

  return (
    <ModalShell
      onClose={onClose}
      overlayClassName={s.overlay}
      className={s.modal}
      labelledBy={titleId}
      overlayProps={{ 'data-shortcuts-overlay': '' }}
    >
        {/* Header */}
        <div className={s.header}>
          <div className={s.headerLeft}>
            <div className={s.iconBox}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="4" width="20" height="16" rx="2" />
                <path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01M8 12h.01M12 12h.01M16 12h.01M7 16h10" />
              </svg>
            </div>
            <div>
              <h2 id={titleId} className={s.title}>Keyboard Shortcuts</h2>
              <p className={s.subtitle}>Navigate faster with these shortcuts</p>
            </div>
          </div>
          <button onClick={onClose} className={s.closeButton} aria-label="Close">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Shortcuts Grid */}
        <div className={s.body}>
          <div className={s.grid}>
            {SHORTCUTS_LIST.map((shortcut, idx) => {
              // Replace "Ctrl" with platform-specific modifier
              const displayKeys = shortcut.keys.map(k =>
                k === 'Ctrl' ? modLabel : k
              );

              return (
                <div key={idx} className={s.row}>
                  <div className={s.keysContainer}>
                    {displayKeys.map((key, ki) => (
                      <React.Fragment key={ki}>
                        {ki > 0 && <span className={s.plus}>+</span>}
                        <kbd className={s.kbd}>{key}</kbd>
                      </React.Fragment>
                    ))}
                  </div>
                  <span className={s.desc}>{shortcut.description}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer hint */}
        <div className={s.footer}>
          Press <kbd className={s.kbdSmall}>?</kbd> to toggle this overlay
        </div>
    </ModalShell>
  );
};
