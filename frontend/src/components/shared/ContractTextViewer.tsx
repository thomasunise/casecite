import { useEffect, useMemo, useRef, useState } from 'react';
import { Icon } from './Icon';
import { PdfDocumentViewer } from './PdfDocumentViewer';
import type { ContractRedlineEdit } from '../../api/types';
import s from './ContractTextViewer.module.css';

export type SelectionAction = 'explain' | 'redline' | 'rewrite' | 'ask';
type RedlineDecisionValue = 'accepted' | 'rejected';
type RedlineState = RedlineDecisionValue | 'pending';

interface ContractTextViewerProps {
  filename: string;
  text: string;
  loading: boolean;
  /** Native PDF render of the file (real formatting); enables the
      Document/Text toggle. Selection tools and redlines live in Text view. */
  fileUrl?: string | null;
  highlights: string[];
  /** Redline edits for this contract; marks render inline + in the side rail. */
  redlines?: ContractRedlineEdit[];
  /** Per-ref decision; missing ref = accepted. */
  redlineDecisions?: Record<string, RedlineDecisionValue>;
  onRedlineDecision?: (ref: string, decision: RedlineDecisionValue) => void;
  /** The user's own wording for proposed edits (ref -> text). */
  proposedOverrides?: Record<string, string>;
  onProposedEdit?: (ref: string, text: string) => void;
  /** Hand-edit the working copy of the contract text. */
  onTextEdit?: (text: string) => void;
  textDirty?: boolean;
  /** Download the document as it currently reads (edited or not) as .docx. */
  onExportEditedCopy?: () => void;
  /** Reports which edit's popover is open, for cross-highlighting. */
  onActiveEditChange?: (ref: string | null) => void;
  onExportRedlines?: () => void;
  exportingRedlines?: boolean;
  onClose: () => void;
  /** Called when the user selects text and picks an action for it. */
  onSelectionAction: (action: SelectionAction, selection: string) => void;
  /** Scroll to and flash the highlight at this index; seq retriggers. */
  jumpToHighlight?: { index: number; seq: number } | null;
  /** Anchor a redline edit (from the right panel); seq retriggers. */
  jumpToEditRef?: { ref: string; seq: number } | null;
}

interface SelectionState {
  text: string;
  top: number;
  left: number;
}

interface PopoverState {
  ref: string;
  top: number;
  /** Set once the user drags the popover; overrides the centered position. */
  left?: number;
}

interface Block {
  start: number;
  end: number;
  kind: 'heading' | 'para';
}

interface MarkSpan {
  start: number;
  end: number;
  kind: 'highlight' | 'redline';
  editRef?: string;
  /** Position of this quote in the highlights array — the anchor id. */
  highlightIndex?: number;
}

interface Segment {
  text: string;
  kind: 'plain' | 'highlight' | 'redline';
  editRef?: string;
  highlightIndex?: number;
}

const HEADING_RE = /^\s*(?:(?:ARTICLE|SECTION|EXHIBIT|SCHEDULE|APPENDIX)\s+[\dIVXLC]+|\d+(?:\.\d+)*[.)]?\s+\S|[A-Z][A-Z0-9 ,;:&()/'-]{3,})\s*$/;

/* Group the extracted text into document blocks: blank lines split
   paragraphs; a short line in caps or numbered like "7.2 Termination" is a
   heading. Rendering paragraphs with normal whitespace re-flows the
   extraction's hard-wrapped lines back into real paragraphs. */
function buildBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let cursor = 0;
  let paraStart = -1;
  const flush = (end: number) => {
    if (paraStart >= 0 && end > paraStart) blocks.push({ start: paraStart, end, kind: 'para' });
    paraStart = -1;
  };
  for (const line of text.split('\n')) {
    const start = cursor;
    const end = cursor + line.length;
    cursor = end + 1;
    const trimmed = line.trim();
    if (!trimmed) { flush(start); continue; }
    if (trimmed.length <= 80 && HEADING_RE.test(trimmed)) {
      flush(start);
      blocks.push({ start, end, kind: 'heading' });
      continue;
    }
    if (paraStart < 0) paraStart = start;
  }
  flush(text.length);
  return blocks;
}

/* Locate a quote in the document by exact match, falling back to a
   whitespace-normalized search (extraction and chunking can differ on line
   breaks). Returns null when the quote cannot be found. */
function locateQuote(text: string, normalizedText: string, quote: string): [number, number] | null {
  if (!quote) return null;
  const start = text.indexOf(quote);
  if (start !== -1) return [start, start + quote.length];
  const normalizedQuote = quote.replace(/\s+/g, ' ').trim();
  const normStart = normalizedText.indexOf(normalizedQuote);
  if (normStart === -1) return null;
  // Map the normalized offset back to the raw text by walking both.
  let raw = 0;
  let norm = 0;
  while (norm < normStart && raw < text.length) {
    if (/\s/.test(text[raw])) {
      while (raw < text.length && /\s/.test(text[raw])) raw++;
      norm++;
    } else {
      raw++;
      norm++;
    }
  }
  return [raw, Math.min(text.length, raw + normalizedQuote.length + 40)];
}

/* Combine highlight + redline quotes into non-overlapping marks; where they
   collide, the redline wins (it is the actionable mark). */
function buildMarkSpans(
  text: string, highlights: string[], redlines: ContractRedlineEdit[]
): MarkSpan[] {
  const normalizedText = text.replace(/\s+/g, ' ');
  const redlineSpans: MarkSpan[] = [];
  for (const edit of redlines) {
    if (edit.kind !== 'replace' || !edit.original_text) continue;
    const located = locateQuote(text, normalizedText, edit.original_text);
    if (located) {
      redlineSpans.push({ start: located[0], end: located[1], kind: 'redline', editRef: edit.ref });
    }
  }
  const highlightSpans: MarkSpan[] = [];
  highlights.forEach((quote, highlightIndex) => {
    const located = locateQuote(text, normalizedText, quote);
    if (!located) return;
    const overlapsRedline = redlineSpans.some(
      (r) => located[0] < r.end && located[1] > r.start
    );
    if (!overlapsRedline) {
      highlightSpans.push({ start: located[0], end: located[1], kind: 'highlight', highlightIndex });
    }
  });
  const all = [...redlineSpans, ...highlightSpans].sort((a, b) => a.start - b.start);
  const merged: MarkSpan[] = [];
  for (const span of all) {
    const last = merged[merged.length - 1];
    if (last && span.start < last.end) continue; // drop overlaps, first wins
    merged.push(span);
  }
  return merged;
}

/* Slice one block into segments from the merged mark spans. */
function blockSegments(text: string, block: Block, spans: MarkSpan[]): Segment[] {
  const segments: Segment[] = [];
  let cursor = block.start;
  for (const span of spans) {
    const s0 = Math.max(span.start, block.start);
    const s1 = Math.min(span.end, block.end);
    if (s1 <= s0) continue;
    if (s0 > cursor) segments.push({ text: text.slice(cursor, s0), kind: 'plain' });
    segments.push({
      text: text.slice(s0, s1), kind: span.kind,
      editRef: span.editRef, highlightIndex: span.highlightIndex,
    });
    cursor = s1;
  }
  if (cursor < block.end) segments.push({ text: text.slice(cursor, block.end), kind: 'plain' });
  return segments;
}

const SEVERITY_ORDER: Record<string, number> = { critical: 0, major: 1, minor: 2 };

export function ContractTextViewer({
  filename, text, loading, fileUrl, highlights,
  redlines, redlineDecisions, onRedlineDecision, onExportRedlines, exportingRedlines,
  proposedOverrides, onProposedEdit, onTextEdit, textDirty, onExportEditedCopy,
  onClose, onSelectionAction, jumpToHighlight, jumpToEditRef, onActiveEditChange,
}: ContractTextViewerProps) {
  const firstMarkRef = useRef<HTMLElement | null>(null);
  const highlightEls = useRef<Record<number, HTMLElement | null>>({});
  const [flashIndex, setFlashIndex] = useState<number | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const editMarkEls = useRef<Record<string, HTMLElement | null>>({});
  const [selection, setSelection] = useState<SelectionState | null>(null);
  const [popover, setPopover] = useState<PopoverState | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [showProposed, setShowProposed] = useState(false);
  // Native document render vs extracted text. Text is the working surface
  // (selection tools, highlights, redlines); Document shows real formatting.
  // Default to the native view only while nothing is anchored to the text.
  const [docMode, setDocMode] = useState<boolean | null>(null);
  const showDoc = !!fileUrl && (docMode ?? (highlights.length === 0 && (redlines?.length ?? 0) === 0));
  // Hand-editing: the proposed wording in the popover, and the whole text.
  const [proposedDraft, setProposedDraft] = useState<string | null>(null);
  const [textDraft, setTextDraft] = useState<string | null>(null);
  const effProposed = (edit: ContractRedlineEdit): string =>
    proposedOverrides?.[edit.ref] ?? edit.proposed_text;
  // Anchoring (citation jumps, redline jumps) lives in the text view — switch
  // to it whenever something asks to be shown in the text.
  useEffect(() => {
    if (jumpToHighlight || jumpToEditRef) setDocMode(false);
  }, [jumpToHighlight, jumpToEditRef]);

  const activeRedlines = useMemo(
    () => (redlines || []).slice().sort(
      (a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3)
    ),
    [redlines],
  );
  const editByRef = useMemo(() => {
    const map: Record<string, ContractRedlineEdit> = {};
    for (const edit of activeRedlines) map[edit.ref] = edit;
    return map;
  }, [activeRedlines]);
  const blocks = useMemo(() => buildBlocks(text), [text]);
  const spans = useMemo(
    () => buildMarkSpans(text, highlights, activeRedlines),
    [text, highlights, activeRedlines],
  );
  const highlightCount = spans.filter((sp) => sp.kind === 'highlight').length;

  useEffect(() => {
    if (!activeRedlines.length) {
      firstMarkRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [spans, activeRedlines.length]);

  // Redline anchoring from the right panel.
  useEffect(() => {
    if (!jumpToEditRef) return;
    const el = editMarkEls.current[jumpToEditRef.ref];
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    openPopoverAt(jumpToEditRef.ref, el);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpToEditRef]);

  // Citation anchoring: the conversation asks, the document answers.
  useEffect(() => {
    if (!jumpToHighlight) return;
    const el = highlightEls.current[jumpToHighlight.index];
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setFlashIndex(jumpToHighlight.index);
    const timer = setTimeout(() => setFlashIndex(null), 1600);
    return () => clearTimeout(timer);
  }, [jumpToHighlight]);

  // Three states: pending (untouched, red mark), accepted (proposed text
  // swaps in immediately), rejected (dimmed original).
  const decisionFor = (ref: string): RedlineState =>
    (redlineDecisions || {})[ref] || 'pending';

  const openPopoverAt = (ref: string, el: HTMLElement | null) => {
    const container = bodyRef.current;
    if (!el || !container) return;
    const rect = el.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    setSelection(null);
    setProposedDraft(null);
    setPopover({ ref, top: rect.bottom - containerRect.top + container.scrollTop + 6 });
    onActiveEditChange?.(ref);
  };

  const closePopover = () => {
    setPopover(null);
    setProposedDraft(null);
    onActiveEditChange?.(null);
  };

  // Drag the popover by its header — it covers text otherwise.
  const dragState = useRef<{ startX: number; startY: number; top: number; left: number } | null>(null);
  const handlePopoverDragStart = (e: React.PointerEvent) => {
    if (!popover || (e.target as HTMLElement).closest('button')) return;
    const el = (e.currentTarget as HTMLElement).parentElement;
    if (!el) return;
    dragState.current = {
      startX: e.clientX,
      startY: e.clientY,
      top: popover.top,
      left: popover.left ?? el.offsetLeft,
    };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const handlePopoverDragMove = (e: React.PointerEvent) => {
    const drag = dragState.current;
    if (!drag || !popover) return;
    setPopover({
      ...popover,
      top: Math.max(0, drag.top + e.clientY - drag.startY),
      left: Math.max(0, drag.left + e.clientX - drag.startX),
    });
  };
  const handlePopoverDragEnd = () => { dragState.current = null; };

  // Select any passage in the document to get contextual actions on it —
  // the Spellbook-style select-and-act interaction.
  const handleMouseUp = () => {
    const sel = window.getSelection();
    const container = bodyRef.current;
    if (!sel || sel.isCollapsed || !container) { setSelection(null); return; }
    const selected = sel.toString().trim();
    if (selected.length < 8 || !container.contains(sel.anchorNode)) { setSelection(null); return; }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    setSelection({
      text: selected.slice(0, 2000),
      top: rect.top - containerRect.top + container.scrollTop - 44,
      left: Math.max(8, rect.left - containerRect.left + rect.width / 2 - 140),
    });
  };

  const act = (action: SelectionAction) => {
    if (!selection) return;
    onSelectionAction(action, selection.text);
    setSelection(null);
    window.getSelection()?.removeAllRanges();
  };

  const popoverEdit = popover ? editByRef[popover.ref] : null;
  const acceptedCount = activeRedlines.filter((e) => decisionFor(e.ref) === 'accepted').length;

  let markIndex = 0;
  const renderedProposed = new Set<string>();

  const renderSegment = (seg: Segment, key: number) => {
    if (seg.kind === 'highlight') {
      const isFirst = markIndex++ === 0;
      const hi = seg.highlightIndex;
      return (
        <mark
          key={key}
          className={hi != null && hi === flashIndex ? s.markFlash : s.mark}
          ref={(el) => {
            if (isFirst) firstMarkRef.current = el;
            if (hi != null) highlightEls.current[hi] = el;
          }}
        >
          {seg.text}
        </mark>
      );
    }
    if (seg.kind === 'redline' && seg.editRef) {
      const edit = editByRef[seg.editRef];
      const decision = decisionFor(seg.editRef);
      const isActive = popover?.ref === seg.editRef;
      if (edit && (decision === 'accepted' || (decision === 'pending' && showProposed))) {
        // Preview mode: the clause reads as it would after accepting.
        if (renderedProposed.has(seg.editRef)) return null;
        renderedProposed.add(seg.editRef);
        return (
          <ins
            key={key}
            className={isActive ? s.proposedInlineActive : s.proposedInline}
            data-edit-ref={seg.editRef}
            ref={(el) => { editMarkEls.current[seg.editRef!] = el; }}
            onClick={(e) => openPopoverAt(seg.editRef!, e.currentTarget)}
          >
            {effProposed(edit)}
          </ins>
        );
      }
      return (
        <mark
          key={key}
          className={
            isActive ? s.redlineMarkActive
              : decision === 'rejected' ? s.redlineRejected
              : s.redlineMark
          }
          title="Proposed edit — click to review"
          data-edit-ref={seg.editRef}
          ref={(el) => { editMarkEls.current[seg.editRef!] = el; }}
          onClick={(e) => openPopoverAt(seg.editRef!, e.currentTarget)}
        >
          {seg.text}
        </mark>
      );
    }
    return <span key={key}>{seg.text}</span>;
  };

  return (
    <aside className={s.viewer} aria-label="Contract text">
      <div className={s.header}>
        <Icon name="FileText" size={14} className={s.headerIcon} />
        <span className={s.filename}>{filename}</span>
        {fileUrl && (
          <span className={s.viewToggle}>
            <button
              className={showDoc ? s.viewToggleActive : s.viewToggleBtn}
              onClick={() => setDocMode(true)}
            >
              Document
            </button>
            <button
              className={!showDoc ? s.viewToggleActive : s.viewToggleBtn}
              onClick={() => setDocMode(false)}
            >
              Text
            </button>
          </span>
        )}
        {activeRedlines.length > 0 ? (
          <>
            <span className={s.highlightCount}>
              {acceptedCount} of {activeRedlines.length} redlines accepted
            </span>
            <button
              className={showProposed ? s.headerToggleActive : s.headerToggle}
              onClick={() => setShowProposed(!showProposed)}
            >
              <Icon name="Eye" size={12} />
              {showProposed ? 'Showing proposed' : 'Show proposed'}
            </button>
            {onExportRedlines && (
              <button
                className={s.headerToggle}
                onClick={onExportRedlines}
                disabled={!!exportingRedlines}
              >
                {exportingRedlines
                  ? <Icon name="Loader2" size={12} className={s.spin} />
                  : <Icon name="Download" size={12} />}
                Export .docx
              </button>
            )}
          </>
        ) : highlightCount > 0 && (
          <span className={s.highlightCount}>
            {highlightCount} highlighted passage{highlightCount === 1 ? '' : 's'}
          </span>
        )}
        {onTextEdit && !loading && textDraft === null && (
          <button
            className={s.headerToggle}
            onClick={() => { setDocMode(false); setTextDraft(text); }}
            title="Edit the contract text directly"
          >
            <Icon name="Pencil" size={12} /> Edit text
          </button>
        )}
        {onExportEditedCopy && !loading && textDraft === null && text && (
          <button
            className={s.headerToggle}
            onClick={onExportEditedCopy}
            title={textDirty ? 'Download your edited copy as a Word document' : 'Download this document as a Word document'}
          >
            <Icon name="Download" size={12} /> {textDirty ? 'Export edited copy' : 'Export to Word'}
          </button>
        )}
        <button
          className={s.closeBtn}
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? 'Expand contract' : 'Collapse contract'}
        >
          <Icon name={collapsed ? 'ChevronDown' : 'ChevronUp'} size={14} />
        </button>
        <button className={s.closeBtn} onClick={onClose} aria-label="Close contract view">
          <Icon name="X" size={14} />
        </button>
      </div>
      {!collapsed && textDraft !== null && onTextEdit && (
        <div className={s.textEditWrap}>
          <textarea
            aria-label="Edit contract text"
            className={s.textEditArea}
            value={textDraft}
            onChange={(e) => setTextDraft(e.target.value)}
          />
          <div className={s.textEditBar}>
            <span className={s.textEditHint}>
              Edits become your working copy — the redline export still tracks
              changes against the original file.
            </span>
            <button
              className={s.popoverEditSave}
              onClick={() => { onTextEdit(textDraft); setTextDraft(null); }}
            >
              <Icon name="Check" size={12} /> Save
            </button>
            <button className={s.popoverEditCancel} onClick={() => setTextDraft(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {!collapsed && textDraft === null && showDoc && fileUrl && (
        <div className={s.docRender}>
          <PdfDocumentViewer fileUrl={fileUrl} />
        </div>
      )}
      {!collapsed && textDraft === null && !showDoc && (
      <div className={s.body} ref={bodyRef} onMouseUp={handleMouseUp}>
        {selection && (
          <div className={s.selectionMenu} style={{ top: selection.top, left: selection.left }}>
            <button className={s.selectionBtn} onClick={() => act('explain')}>
              <Icon name="Lightbulb" size={12} /> Explain
            </button>
            <button className={s.selectionBtn} onClick={() => act('redline')}>
              <Icon name="FilePen" size={12} /> Redline
            </button>
            <button className={s.selectionBtn} onClick={() => act('rewrite')}>
              <Icon name="Wand2" size={12} /> Rewrite
            </button>
            <button className={s.selectionBtn} onClick={() => act('ask')}>
              <Icon name="MessageSquare" size={12} /> Ask…
            </button>
          </div>
        )}
        {popover && popoverEdit && (
          <div
            className={popover.left != null ? s.redlinePopoverDragged : s.redlinePopover}
            style={popover.left != null ? { top: popover.top, left: popover.left } : { top: popover.top }}
          >
            <div
              className={s.popoverHead}
              onPointerDown={handlePopoverDragStart}
              onPointerMove={handlePopoverDragMove}
              onPointerUp={handlePopoverDragEnd}
            >
              <Icon name="GripHorizontal" size={12} className={s.dragGrip} />
              <span className={s.popoverTitle}>{popoverEdit.title}</span>
              <button className={s.closeBtn} onClick={closePopover} aria-label="Close">
                <Icon name="X" size={12} />
              </button>
            </div>
            {popoverEdit.source && (
              <p className={s.popoverSource}>{popoverEdit.source}</p>
            )}
            {popoverEdit.rationale && <p className={s.popoverWhy}>{popoverEdit.rationale}</p>}
            {proposedDraft !== null && onProposedEdit ? (
              <>
                <textarea
                  aria-label="Edit proposed text"
                  className={s.popoverProposedEdit}
                  value={proposedDraft}
                  onChange={(e) => setProposedDraft(e.target.value)}
                  rows={Math.min(12, Math.max(4, proposedDraft.split('\n').length + 1))}
                />
                <div className={s.popoverEditActions}>
                  <button
                    className={s.popoverEditSave}
                    onClick={() => {
                      onProposedEdit(popoverEdit.ref, proposedDraft.trim() || popoverEdit.proposed_text);
                      setProposedDraft(null);
                    }}
                  >
                    <Icon name="Check" size={12} /> Save wording
                  </button>
                  <button className={s.popoverEditCancel} onClick={() => setProposedDraft(null)}>
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <div className={s.popoverProposed}>
                {effProposed(popoverEdit)}
                {onProposedEdit && (
                  <button
                    className={s.popoverEditBtn}
                    onClick={() => setProposedDraft(effProposed(popoverEdit))}
                    title="Edit the proposed wording"
                  >
                    <Icon name="Pencil" size={11} />
                    {proposedOverrides?.[popoverEdit.ref] ? 'Edited — change' : 'Edit'}
                  </button>
                )}
              </div>
            )}
            {onRedlineDecision && (
              <div className={s.popoverActions}>
                <button
                  className={decisionFor(popoverEdit.ref) === 'accepted' ? s.acceptBtnActive : s.acceptBtn}
                  onClick={() => onRedlineDecision(popoverEdit.ref, 'accepted')}
                >
                  <Icon name="Check" size={12} /> Accept
                </button>
                <button
                  className={decisionFor(popoverEdit.ref) === 'rejected' ? s.rejectBtnActive : s.rejectBtn}
                  onClick={() => onRedlineDecision(popoverEdit.ref, 'rejected')}
                >
                  <Icon name="X" size={12} /> Reject
                </button>
              </div>
            )}
          </div>
        )}
        {loading ? (
          <div className={s.loading}>
            <Icon name="Loader2" size={16} className={s.spin} /> Loading contract…
          </div>
        ) : (
          <div className={s.text}>
              {blocks.map((block, bi) => {
                const segments = blockSegments(text, block, spans);
                const content = segments.map((seg, i) => renderSegment(seg, i));
                return block.kind === 'heading' ? (
                  <div key={bi} className={s.heading}>{content}</div>
                ) : (
                  <p key={bi} className={s.para}>{content}</p>
                );
              })}
            </div>
        )}
      </div>
      )}
    </aside>
  );
}
