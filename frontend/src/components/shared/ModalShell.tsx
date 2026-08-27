import {
  useEffect, useRef,
  type HTMLAttributes, type MouseEvent as ReactMouseEvent, type ReactNode, type RefObject,
} from 'react';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

/** Open shells, innermost last — only the topmost one reacts to Escape and Tab. */
const openShells: symbol[] = [];

export interface ModalShellProps {
  /** Render nothing when false. Defaults to true so callers may keep their own early return. */
  isOpen?: boolean;
  onClose: () => void;
  /** The modal's existing full-screen overlay class. */
  overlayClassName?: string;
  /** The modal's existing dialog panel class. */
  className?: string;
  /** id of the visible title element — wired to aria-labelledby. */
  labelledBy?: string;
  /** Accessible name for dialogs without a visible title. */
  label?: string;
  describedBy?: string;
  /** Element to focus on open. Defaults to the first focusable element, else the panel. */
  initialFocusRef?: RefObject<HTMLElement | null>;
  /** Clicking the backdrop calls onClose (default true). */
  closeOnBackdrop?: boolean;
  /** Escape calls onClose (default true). */
  closeOnEscape?: boolean;
  /** Extra attributes for the overlay element (e.g. data-* hooks). */
  overlayProps?: HTMLAttributes<HTMLDivElement> & Record<`data-${string}`, string | undefined>;
  children: ReactNode;
}

/**
 * Accessible dialog chrome shared by every modal: role="dialog" + aria-modal,
 * focus moved inside on open and restored on close, a Tab/Shift+Tab focus
 * trap, Escape and backdrop-click dismissal. Each modal keeps its own CSS
 * classes; the shell only adds the `modal-shell-*` / `*-responsive` hooks
 * used by styles/responsive.css (reduced motion, small-screen sizing).
 *
 * Escape is handled once, at document level, and its propagation is stopped so
 * the window-level shortcut handler (useKeyboardShortcuts) does not close the
 * same modal a second time. With stacked dialogs only the topmost responds.
 */
export function ModalShell({ isOpen = true, ...rest }: ModalShellProps) {
  if (!isOpen) return null;
  return <ModalShellInner {...rest} />;
}

function ModalShellInner({
  onClose, overlayClassName, className, labelledBy, label, describedBy,
  initialFocusRef, closeOnBackdrop = true, closeOnEscape = true, overlayProps, children,
}: Omit<ModalShellProps, 'isOpen'>) {
  const panelRef = useRef<HTMLDivElement>(null);
  const tokenRef = useRef<symbol | null>(null);
  if (tokenRef.current === null) tokenRef.current = Symbol('modal-shell');
  const mouseDownTarget = useRef<EventTarget | null>(null);

  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  // Register on the stack, move focus in, restore it when the dialog unmounts.
  useEffect(() => {
    const token = tokenRef.current as symbol;
    openShells.push(token);
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = panelRef.current;
    // Respect an autoFocus that already landed inside the dialog.
    if (panel && !panel.contains(document.activeElement)) {
      const target = initialFocusRef?.current ?? panel.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ?? panel;
      target.focus();
    }
    return () => {
      const i = openShells.indexOf(token);
      if (i !== -1) openShells.splice(i, 1);
      if (previouslyFocused && previouslyFocused.isConnected) previouslyFocused.focus();
    };
  }, [initialFocusRef]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (openShells[openShells.length - 1] !== tokenRef.current) return;

      if (e.key === 'Escape') {
        if (!closeOnEscape) return;
        e.preventDefault();
        e.stopPropagation();
        onCloseRef.current();
        return;
      }

      if (e.key !== 'Tab') return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      e.preventDefault();
      if (focusable.length === 0) { panel.focus(); return; }
      // Walk the ring from the current element; skip anything the browser
      // refuses to focus (hidden inputs, etc.) and wrap at either end.
      const n = focusable.length;
      const current = document.activeElement instanceof HTMLElement ? focusable.indexOf(document.activeElement) : -1;
      const step = e.shiftKey ? -1 : 1;
      const start = current === -1 ? (e.shiftKey ? n - 1 : 0) : current + step;
      for (let k = 0; k < n; k++) {
        const el = focusable[(((start + k * step) % n) + n) % n];
        el.focus();
        if (document.activeElement === el) return;
      }
      panel.focus();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [closeOnEscape]);

  const handleOverlayMouseDown = (e: ReactMouseEvent<HTMLDivElement>) => {
    mouseDownTarget.current = e.target;
  };
  const handleOverlayClick = (e: ReactMouseEvent<HTMLDivElement>) => {
    const startedOn = mouseDownTarget.current;
    mouseDownTarget.current = null;
    if (!closeOnBackdrop || e.target !== e.currentTarget) return;
    // A drag that began inside the panel (text selection) and was released
    // over the backdrop is not a dismissal.
    if (startedOn && startedOn !== e.currentTarget) return;
    onClose();
  };

  return (
    <div
      {...overlayProps}
      className={`${overlayClassName ?? ''} modal-shell-overlay modal-overlay-responsive`.trim()}
      onMouseDown={handleOverlayMouseDown}
      onClick={handleOverlayClick}
    >
      <div
        ref={panelRef}
        className={`${className ?? ''} modal-shell-panel modal-container-responsive`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={label}
        aria-describedby={describedBy}
        tabIndex={-1}
      >
        {children}
      </div>
    </div>
  );
}
