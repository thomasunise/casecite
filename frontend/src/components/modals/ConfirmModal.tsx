import { useRef } from 'react';
import { ModalShell } from '../shared/ModalShell';
import s from './ConfirmModal.module.css';

interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm?: () => void;
  title?: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  type?: 'info' | 'warning' | 'danger';
}

const ConfirmModal = ({
  isOpen,
  onClose,
  onConfirm,
  title = 'Confirm',
  message = '',
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  type = 'info',
}: ConfirmModalProps) => {
  const confirmBtnRef = useRef<HTMLButtonElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);

  if (!isOpen) return null;

  const typeColors = {
    info: '#4A9EFF',
    warning: '#F5A623',
    danger: '#E74C3C',
  };

  const confirmColor = typeColors[type] || typeColors.info;

  const typeIcons = {
    info: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={confirmColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
    ),
    warning: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={confirmColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    ),
    danger: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={confirmColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="15" y1="9" x2="9" y2="15" />
        <line x1="9" y1="9" x2="15" y2="15" />
      </svg>
    ),
  };

  return (
    <ModalShell
      onClose={onClose}
      overlayClassName={s.overlay}
      className={s.modal}
      labelledBy="confirm-modal-title"
      describedBy="confirm-modal-message"
      // Focus the cancel button (safer default) or confirm for info-only modals
      initialFocusRef={onConfirm ? cancelBtnRef : confirmBtnRef}
    >
        <div className={s.iconWrapper}>
          <div className={s.iconCircle} style={{ background: `${confirmColor}15` }}>
            {typeIcons[type] || typeIcons.info}
          </div>
        </div>

        <h2 id="confirm-modal-title" className={s.title}>{title}</h2>
        <p id="confirm-modal-message" className={s.message}>{message}</p>

        <div className={s.buttonRow}>
          {onConfirm && (
            <button
              ref={cancelBtnRef}
              className={s.cancelButton}
              onClick={onClose}
            >
              {cancelText}
            </button>
          )}
          <button
            ref={confirmBtnRef}
            className={s.confirmButton}
            style={{ background: confirmColor }}
            onClick={() => {
              if (onConfirm) {
                onConfirm();
              } else {
                onClose();
              }
            }}
          >
            {onConfirm ? confirmText : 'OK'}
          </button>
        </div>
    </ModalShell>
  );
};

export { ConfirmModal };
