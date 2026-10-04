import React from 'react';
import { Icon } from './Icon';
import { ExportMenu } from './ExportMenu';
import type { ConversationExportFormat } from '../../api/types';
import s from './FloatingChatDock.module.css';

interface FloatingChatDockProps {
  open: boolean;
  /** The composer is hidden — sit lower on the page. */
  low?: boolean;
  busy?: boolean;
  count: number;
  onMinimize: () => void;
  onExpand: () => void;
  /** Wipe the conversation and start fresh. Renders the Clear control. */
  onClear?: () => void;
  /** Download the conversation as Word / PDF / Markdown. Renders the Export menu. */
  onExport?: (format: ConversationExportFormat) => void;
  exporting?: boolean;
  /** Extra root class, e.g. to override --dock-bottom / --dock-bottom-low. */
  className?: string;
  children: React.ReactNode;
}

function FloatingChatDock({
  open, low, busy, count, onMinimize, onExpand, onClear, onExport, exporting, className, children,
}: FloatingChatDockProps) {
  if (!open) {
    return (
      <button
        className={`${low ? s.bubbleLow : s.bubble} ${className || ''}`}
        onClick={onExpand}
        aria-label="Open conversation"
      >
        {busy
          ? <Icon name="Loader2" size={18} className={s.spin} />
          : <Icon name="MessageSquare" size={18} />}
        <span className={s.bubbleCount}>{count}</span>
      </button>
    );
  }

  return (
    <>
      {/* Blur the page behind the open conversation; clicking the blur
          minimizes the chat and refocuses the document. */}
      <div className={s.backdrop} onClick={onMinimize} aria-hidden="true" />
      <div className={`${low ? s.overlayLow : s.overlay} ${className || ''}`}>
        <div className={s.header}>
          <Icon name="MessageSquare" size={13} />
          <span>Conversation</span>
          <span className={s.spacer} />
          {onExport && count > 0 && (
            <span className={s.exportSlot}>
              <ExportMenu onExport={onExport} busy={exporting} />
            </span>
          )}
          {onClear && (
            <button
              className={s.clearBtn}
              onClick={onClear}
              disabled={busy}
              title="Clear the conversation and start fresh"
              aria-label="Clear conversation"
            >
              <Icon name="Eraser" size={13} /> Clear
            </button>
          )}
          <button className={s.minBtn} onClick={onMinimize} aria-label="Minimize conversation">
            <Icon name="Minus" size={14} />
          </button>
        </div>
        <div className={s.body}>{children}</div>
      </div>
    </>
  );
}

export { FloatingChatDock };
