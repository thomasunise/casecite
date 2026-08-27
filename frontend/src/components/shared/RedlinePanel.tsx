import { useState } from 'react';
import { Icon } from './Icon';
import { AiNotice } from './AiNotice';
import { useContractsStore } from '../../stores/contractsStore';
import s from './RedlinePanel.module.css';

/* The redlines rail, living in the app's right panel: replace-edits anchor
   into the document on click; proposed additions expand in place with
   accept/reject (they have no anchor point in the document). */
export function RedlinePanel() {
  const getActiveRedlines = useContractsStore((st) => st.getActiveRedlines);
  const redlineDecisions = useContractsStore((st) => st.redlineDecisions);
  const redlineOverrides = useContractsStore((st) => st.redlineOverrides);
  const requestEditJump = useContractsStore((st) => st.requestEditJump);
  const setRedlineDecision = useContractsStore((st) => st.setRedlineDecision);
  const exportRedlineDocx = useContractsStore((st) => st.exportRedlineDocx);
  const exporting = useContractsStore((st) => st.exporting);
  const activeEditRef = useContractsStore((st) => st.activeEditRef);
  const [openInsert, setOpenInsert] = useState<string | null>(null);

  const active = getActiveRedlines();
  if (!active) {
    return (
      <div className={s.empty}>
        <Icon name="FilePen" size={28} className={s.emptyIcon} />
        <p>No redlines yet — pick the Redline mode, give your instructions, and they'll land here.</p>
      </div>
    );
  }

  const { analysisId, edits } = active;
  const decisionFor = (ref: string) => redlineDecisions[`${analysisId}:${ref}`] || 'pending';
  const replaceEdits = edits.filter((e) => e.kind !== 'insert');
  const insertEdits = edits.filter((e) => e.kind === 'insert');
  const accepted = edits.filter((e) => decisionFor(e.ref) === 'accepted').length;

  return (
    <div className={s.panel}>
      <div className={s.header}>
        <span className={s.count}>{accepted} of {edits.length} accepted</span>
        <button
          className={s.exportBtn}
          onClick={() => exportRedlineDocx(analysisId)}
          disabled={exporting}
        >
          {exporting
            ? <Icon name="Loader2" size={12} className={s.spin} />
            : <Icon name="Download" size={12} />}
          Export .docx
        </button>
      </div>

      {replaceEdits.length > 0 && <div className={s.sectionTitle}>Redlines</div>}
      {replaceEdits.map((edit) => {
        const state = decisionFor(edit.ref);
        return (
          <button
            key={edit.ref}
            className={`${
              state === 'rejected' ? s.chipRejected
                : state === 'accepted' ? s.chipAccepted
                : s.chip
            } ${activeEditRef === edit.ref ? s.chipActive : ''}`}
            onClick={() => requestEditJump(edit.ref)}
            title={edit.rationale || edit.title || ''}
          >
            {state === 'accepted' && <Icon name="Check" size={11} className={s.checkIcon} />}
            <span className={s.chipText}>{edit.title}</span>
          </button>
        );
      })}

      {insertEdits.length > 0 && <div className={s.sectionTitle}>Additions</div>}
      {insertEdits.map((edit) => {
        const state = decisionFor(edit.ref);
        const open = openInsert === edit.ref;
        return (
          <div key={edit.ref} className={state === 'rejected' ? s.insertRejected : s.insert}>
            <button
              className={s.insertHead}
              onClick={() => setOpenInsert(open ? null : edit.ref)}
            >
              {state === 'accepted'
                ? <Icon name="Check" size={11} className={s.checkIcon} />
                : <Icon name="Plus" size={11} className={s.plusIcon} />}
              <span className={s.chipText}>{edit.title}</span>
              <Icon name={open ? 'ChevronUp' : 'ChevronDown'} size={11} />
            </button>
            {open && (
              <div className={s.insertBody}>
                {edit.rationale && <p className={s.insertWhy}>{edit.rationale}</p>}
                <div className={s.insertProposed}>
                  {redlineOverrides[`${analysisId}:${edit.ref}`] ?? edit.proposed_text}
                </div>
                <div className={s.insertActions}>
                  <button
                    className={state === 'accepted' ? s.acceptActive : s.accept}
                    onClick={() => setRedlineDecision(analysisId, edit.ref, 'accepted')}
                  >
                    <Icon name="Check" size={11} /> Accept
                  </button>
                  <button
                    className={state === 'rejected' ? s.rejectActive : s.reject}
                    onClick={() => setRedlineDecision(analysisId, edit.ref, 'rejected')}
                  >
                    <Icon name="X" size={11} /> Reject
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
      <AiNotice />
    </div>
  );
}
