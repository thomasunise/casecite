import { useState, useEffect, useCallback, useId } from 'react';
import { api } from '../../../api';
import { useUIStore } from '../../../stores/uiStore';
import { Icon } from '../../shared/Icon';
import { downloadBlob } from '../../../utils/downloadBlob';
import { parseUtcDate } from '../../../utils';
import type { AdminUser, AuditLogEntry, AuditLogQuery, AuditVerifyResult } from '../../../api/types';

interface AuditTabProps {
  s: Record<string, string>;
}

// Offered as suggestions; the field accepts any event type the server knows.
const EVENT_TYPE_SUGGESTIONS = [
  'auth.login.success', 'auth.login.failure', 'auth.logout', 'auth.mfa.enabled', 'auth.mfa.disabled',
  'auth.password.change', 'auth.password.reset.complete',
  'document.view', 'document.download', 'document.upload', 'document.delete', 'chat.query',
  'connector.connect', 'connector.sync.start', 'settings.change',
  'user.create', 'user.update', 'user.delete', 'user.role.change', 'user.deactivate',
  'apikey.created', 'apikey.deleted',
  'security.access.denied', 'security.data.export', 'security.alert', 'compliance.audit.access',
];

const PAGE_SIZE = 200;

/** A `<input type="date">` value as the UTC bound the server expects. */
function dayBound(date: string, end: boolean): string | undefined {
  if (!date) return undefined;
  return `${date}T${end ? '23:59:59' : '00:00:00'}Z`;
}

function formatTimestamp(raw: string): string {
  // Stored timestamps look like "…+00:00Z"; drop the redundant Z before parsing.
  const date = parseUtcDate(raw.replace(/([+-]\d{2}:\d{2})Z$/, '$1'));
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleString();
}

function summarizeDetails(entry: AuditLogEntry): string {
  const parts: string[] = [];
  if (entry.resource?.type) parts.push(entry.resource.id ? `${entry.resource.type} ${entry.resource.id}` : entry.resource.type);
  const action = entry.action ?? {};
  for (const [key, value] of Object.entries(action)) {
    if (value === null || value === undefined || typeof value === 'object') continue;
    parts.push(`${key}: ${String(value)}`);
  }
  if (entry.outcome?.error) parts.push(`error: ${entry.outcome.error}`);
  return parts.join(' · ');
}

/**
 * Admin view of the tamper-evident audit trail: filter it, verify the hash
 * chain, and export a range for retention outside the instance. Reading,
 * verifying and exporting the trail are themselves audited by the server.
 */
export const AuditTab = ({ s }: AuditTabProps) => {
  const id = useId();
  const addToast = useUIStore((st) => st.addToast);

  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [eventType, setEventType] = useState('');
  const [userId, setUserId] = useState('');
  const [users, setUsers] = useState<AdminUser[]>([]);

  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<AuditVerifyResult | null>(null);
  const [exporting, setExporting] = useState(false);

  const query = useCallback((): AuditLogQuery => ({
    startDate: dayBound(startDate, false),
    endDate: dayBound(endDate, true),
    eventType: eventType.trim() || undefined,
    userId: userId || undefined,
  }), [startDate, endDate, eventType, userId]);

  const search = useCallback(async (q: AuditLogQuery) => {
    setLoading(true);
    try {
      const res = await api.getAuditLogs({ ...q, limit: PAGE_SIZE });
      setLogs(res.logs);
      setLoaded(true);
    } catch (e) {
      addToast(e instanceof Error ? e.message : 'Failed to load the audit log', 'error');
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  // Newest entries on open; the user list only feeds the filter.
  useEffect(() => {
    search({});
    api.getUsers().then((res) => setUsers(res.users)).catch(() => { /* filter falls back to "anyone" */ });
  }, [search]);

  const handleVerify = async () => {
    setVerifying(true);
    setVerifyResult(null);
    try {
      const q = query();
      setVerifyResult(await api.verifyAuditChain({ startDate: q.startDate, endDate: q.endDate }));
    } catch (e) {
      addToast(e instanceof Error ? e.message : 'Verification could not be run', 'error');
    } finally {
      setVerifying(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const blob = await api.exportAuditLogs(query());
      const range = [startDate || 'start', endDate || 'now'].join('_to_');
      downloadBlob(blob, `casecite-audit-${range}.jsonl`);
    } catch (e) {
      addToast(e instanceof Error ? e.message : 'Audit export failed', 'error');
    } finally {
      setExporting(false);
    }
  };

  const emailFor = (entry: AuditLogEntry) =>
    entry.user?.email || users.find(u => u.id === entry.user?.id)?.email || entry.user?.id || '—';

  return (
    <div className={s.usersTabContent}>
      <div className={s.inviteCard}>
        <div className={s.keyStatusTitle}>Audit Log</div>
        <span className={s.helpText}>
          Every sign-in, document access, export and administrative change is recorded in a
          hash-chained trail. Dates are UTC. Viewing, verifying and exporting the trail are recorded too.
        </span>
        <form
          className={s.auditFilters}
          onSubmit={e => { e.preventDefault(); search(query()); }}
        >
          <div className={s.inviteField}>
            <label className={s.settingLabel} htmlFor={`${id}-from`}>From</label>
            <input id={`${id}-from`} type="date" className={s.modalInput} value={startDate} max={endDate || undefined}
              onChange={e => setStartDate(e.target.value)} />
          </div>
          <div className={s.inviteField}>
            <label className={s.settingLabel} htmlFor={`${id}-to`}>To</label>
            <input id={`${id}-to`} type="date" className={s.modalInput} value={endDate} min={startDate || undefined}
              onChange={e => setEndDate(e.target.value)} />
          </div>
          <div className={s.inviteField}>
            <label className={s.settingLabel} htmlFor={`${id}-event`}>Event type</label>
            <input id={`${id}-event`} className={s.modalInput} value={eventType} list={`${id}-events`}
              onChange={e => setEventType(e.target.value)} placeholder="Any" autoComplete="off" />
            <datalist id={`${id}-events`}>
              {EVENT_TYPE_SUGGESTIONS.map(t => <option key={t} value={t} />)}
            </datalist>
          </div>
          <div className={s.inviteField}>
            <label className={s.settingLabel} htmlFor={`${id}-user`}>User</label>
            <select id={`${id}-user`} className={s.select} value={userId} onChange={e => setUserId(e.target.value)}>
              <option value="">Anyone</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.email}</option>)}
            </select>
          </div>
          <button type="submit" className={s.btnPrimary} disabled={loading}>
            <Icon name="Search" size={14} /> {loading ? 'Loading…' : 'Search'}
          </button>
        </form>

        <div className={s.boxActions}>
          <button className={s.btnSecondaryXSmall} onClick={handleVerify} disabled={verifying}>
            <Icon name="ShieldCheck" size={12} /> {verifying ? 'Verifying…' : 'Verify integrity'}
          </button>
          <button className={s.btnSecondaryXSmall} onClick={handleExport} disabled={exporting}>
            <Icon name="Download" size={12} /> {exporting ? 'Exporting…' : 'Export (JSONL)'}
          </button>
        </div>

        {verifyResult && (
          <div
            className={`${s.auditResult} ${verifyResult.valid ? s.auditResultOk : s.auditResultBad}`}
            role={verifyResult.valid ? 'status' : 'alert'}
          >
            {verifyResult.valid ? (
              <>
                <strong>Integrity verified.</strong> {verifyResult.entries_checked.toLocaleString()} entries checked
                {startDate || endDate ? ' in the selected date range' : ''}; the hash chain is intact.
              </>
            ) : (
              <>
                <strong>Integrity check failed.</strong> {verifyResult.reason || 'An entry was altered, inserted or removed after it was written.'}
                {verifyResult.first_invalid_id && <> First affected entry: <code>{verifyResult.first_invalid_id}</code>.</>}
                {' '}Treat this as a security incident and follow your incident-response procedure.
              </>
            )}
            {!!verifyResult.legacy_entries && (
              <> {verifyResult.legacy_entries.toLocaleString()} older entries predate chain linking: their
              signatures were checked, but their order could not be.</>
            )}
            {verifyResult.truncated && (
              <> The range holds more entries than one verification scans — only the newest were
              checked. Narrow the dates to verify the rest.</>
            )}
          </div>
        )}
      </div>

      <div>
        <div className={s.keyStatusTitle}>
          {loaded ? `${logs.length} ${logs.length === 1 ? 'entry' : 'entries'}, newest first` : 'Entries'}
          {logs.length === PAGE_SIZE && <span className={s.helpText}> — showing the newest {PAGE_SIZE}; narrow the filters or export for the full range</span>}
        </div>
        {loaded && logs.length === 0 && <span className={s.helpText}>No entries match these filters.</span>}
        {logs.length > 0 && (
          <div className={s.permTableWrap}>
            <table className={s.auditTable}>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Event</th>
                  <th>User</th>
                  <th>IP</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((entry) => (
                  <tr key={entry.id}>
                    <td>{formatTimestamp(entry.timestamp)}</td>
                    <td className={entry.outcome?.success === false ? s.auditFailed : undefined}>
                      {entry.event_type}{entry.outcome?.success === false ? ' (failed)' : ''}
                    </td>
                    <td>{emailFor(entry)}</td>
                    <td>{entry.context?.ip_address || '—'}</td>
                    <td>{summarizeDetails(entry)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
