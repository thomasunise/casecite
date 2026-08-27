import { useEffect } from 'react';
import { useWorkspaceSessionsStore } from '../../stores/workspaceSessionsStore';
import { LEGAL_TOOLS } from '../../constants/tools';
import { Icon } from './Icon';
import s from './WorkspaceSessionsList.module.css';

const SURFACE_LABELS: Record<string, string> = {
  contracts: 'Contracts',
  drafting: 'Drafting',
  judge: 'Judge Intel',
  case: 'Case',
};

function surfaceLabel(surface: string): string {
  if (surface.startsWith('tool:')) {
    const toolId = surface.slice('tool:'.length);
    const tool = LEGAL_TOOLS.find((t) => t.id === toolId);
    return tool?.name || toolId;
  }
  return SURFACE_LABELS[surface] || surface;
}

function timeLabel(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const today = new Date();
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString();
}

/**
 * Universal History: every surface's saved sessions — contracts (incl.
 * drafts), each legal tool's search + chat, judge intel, case pages.
 * Clicking one rebuilds that exact session where it lived.
 */
export function WorkspaceSessionsList() {
  const { sessions, loading, restoringId, init, restoreSession, deleteSession } =
    useWorkspaceSessionsStore();

  useEffect(() => { init(); }, [init]);

  if (loading && sessions.length === 0) {
    return <p className={s.empty}><Icon name="Loader2" size={13} className={s.spin} /> Loading…</p>;
  }
  if (sessions.length === 0) {
    return (
      <p className={s.empty}>
        Sessions from Contracts, the Legal Tools, Judge Intel, and case pages
        will appear here — click one to pick up exactly where you left off.
      </p>
    );
  }

  return (
    <div className={s.list}>
      {sessions.map((session) => (
        <div key={session.id} className={s.row}>
          <button
            className={s.rowMain}
            onClick={() => restoreSession(session.id)}
            disabled={restoringId != null}
            title="Reopen this session exactly where you left off"
          >
            {restoringId === session.id
              ? <Icon name="Loader2" size={13} className={s.spin} />
              : <span className={s.badge}>{surfaceLabel(session.surface)}</span>}
            <span className={s.rowText}>
              <span className={s.title}>{session.title}</span>
              <span className={s.time}>{timeLabel(session.updated_at)}</span>
            </span>
          </button>
          <button
            className={s.deleteBtn}
            onClick={() => deleteSession(session.id)}
            aria-label="Delete session"
            title="Delete this session"
          >
            <Icon name="Trash2" size={13} />
          </button>
        </div>
      ))}
    </div>
  );
}
