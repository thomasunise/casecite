import { useEffect, useState, useCallback } from 'react';
import { api } from '../../../api';
import { useMfaStore } from '../../../stores/mfaStore';
import { useAuthStore } from '../../../stores/authStore';
import { useUIStore } from '../../../stores/uiStore';
import { parseUtcDate } from '../../../utils';
import type { SessionInfo } from '../../../api/types';
import { Icon } from '../../shared/Icon';
import t from './SecurityTab.module.css';

interface SecurityTabProps {
  s: Record<string, string>;
}

export function SecurityTab({ s }: SecurityTabProps) {
  const {
    enabled, recoveryCodesRemaining, loading,
    setup, qrDataUrl, enrollCode, setEnrollCode,
    freshRecoveryCodes, dismissRecoveryCodes,
    manageCode, setManageCode, managePassword, setManagePassword,
    loadStatus, beginSetup, cancelSetup, confirmEnable, disable, regenerateCodes,
  } = useMfaStore();
  const enrollmentRequired = useAuthStore((st) => !!st.user?.mfa_enrollment_required);
  const setShowChangePassword = useAuthStore((st) => st.setShowChangePassword);
  const handleLogoutEverywhere = useAuthStore((st) => st.handleLogoutEverywhere);
  const { setShowSettings, showConfirm } = useUIStore();

  const [sessions, setSessions] = useState<SessionInfo[] | null>(null);
  const loadSessions = useCallback(async () => {
    try {
      setSessions((await api.getSessions()).sessions);
    } catch {
      setSessions(null);
    }
  }, []);

  useEffect(() => { loadStatus(); loadSessions(); }, [loadStatus, loadSessions]);

  const openChangePassword = () => {
    // One dialog at a time: the password form replaces Settings.
    setShowSettings(false);
    setShowChangePassword(true);
  };

  const confirmSignOutEverywhere = () => {
    showConfirm({
      title: 'Sign out everywhere?',
      message: 'Every session for your account is ended on all devices, including this one. You will need to sign in again.',
      type: 'warning',
      confirmText: 'Sign out everywhere',
      onConfirm: () => { setShowSettings(false); handleLogoutEverywhere(); },
    });
  };

  const downloadCodes = () => {
    if (!freshRecoveryCodes) return;
    const blob = new Blob(
      [`CaseCite two-factor recovery codes\nEach code works exactly once. Store them somewhere safe.\n\n${freshRecoveryCodes.join('\n')}\n`],
      { type: 'text/plain' },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'casecite-recovery-codes.txt';
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyCodes = () => {
    if (!freshRecoveryCodes) return;
    navigator.clipboard?.writeText(freshRecoveryCodes.join('\n'));
  };

  return (
    <div className={s.tabPanel}>
      {/* Password */}
      <div className={t.managePanel}>
        <div className={t.manageHeading}>Password</div>
        <p className={t.manageNote}>
          Changing your password signs you out on every device; you then sign in again with the new one.
        </p>
        <div className={t.enrollActions}>
          <button className={t.btnGhost} onClick={openChangePassword}>
            <Icon name="KeyRound" size={14} /> Change password
          </button>
        </div>
      </div>

      {/* Sessions */}
      <div className={t.managePanel}>
        <div className={t.manageHeading}>Active sessions</div>
        {sessions === null ? (
          <p className={t.manageNote}>Could not load your sessions.</p>
        ) : sessions.length === 0 ? (
          <p className={t.manageNote}>No active sessions were reported.</p>
        ) : (
          <ul className={t.sessionList}>
            {sessions.map((session, i) => (
              <li key={`${session.created_at}-${i}`} className={t.sessionRow}>
                <span>Signed in {parseUtcDate(session.created_at).toLocaleString()}</span>
                <span className={t.sessionMeta}>
                  last active {parseUtcDate(session.last_activity).toLocaleString()} · {session.ip_address || 'unknown address'}
                  {session.expires_at && ` · ends ${parseUtcDate(session.expires_at).toLocaleString()}`}
                </span>
              </li>
            ))}
          </ul>
        )}
        <div className={t.enrollActions}>
          <button className={t.btnDanger} onClick={confirmSignOutEverywhere}>
            <Icon name="LogOut" size={14} /> Sign out everywhere
          </button>
        </div>
      </div>

      {enrollmentRequired && !enabled && (
        <div className={t.warnBox} role="alert">
          <Icon name="AlertTriangle" size={14} />
          Your firm requires two-factor authentication. Set it up below to keep using your account.
        </div>
      )}

      <p className={t.intro}>
        Two-factor authentication protects your account with a time-based code from an
        authenticator app (1Password, Google Authenticator, Authy, Microsoft Authenticator)
        in addition to your password. Codes are generated on your device — nothing is sent
        by SMS or email.
      </p>

      {/* Status row */}
      <div className={t.statusRow}>
        <div className={`${t.statusDot} ${enabled ? t.dotOn : t.dotOff}`} />
        <span className={t.statusLabel}>
          {enabled ? 'Two-factor authentication is on' : 'Two-factor authentication is off'}
        </span>
        {enabled && (
          <span className={t.recoveryCount}>
            {recoveryCodesRemaining} recovery {recoveryCodesRemaining === 1 ? 'code' : 'codes'} left
          </span>
        )}
      </div>

      {enabled && recoveryCodesRemaining <= 2 && (
        <div className={t.warnBox}>
          <Icon name="AlertTriangle" size={14} />
          You are running low on recovery codes. Generate a new set below.
        </div>
      )}

      {/* Fresh recovery codes — shown exactly once */}
      {freshRecoveryCodes && (
        <div className={t.codesPanel}>
          <div className={t.codesHeading}>
            <Icon name="KeyRound" size={14} /> Recovery codes — save these now
          </div>
          <p className={t.codesNote}>
            Each code signs you in once if you lose your authenticator. They are shown only
            this once and stored hashed, so they cannot be retrieved later.
          </p>
          <div className={t.codesGrid}>
            {freshRecoveryCodes.map((code) => (
              <code key={code} className={t.code}>{code}</code>
            ))}
          </div>
          <div className={t.codesActions}>
            <button className={t.btnGhost} onClick={copyCodes}>
              <Icon name="Copy" size={14} /> Copy
            </button>
            <button className={t.btnGhost} onClick={downloadCodes}>
              <Icon name="Download" size={14} /> Download
            </button>
            <button className={t.btnConfirm} onClick={dismissRecoveryCodes}>
              I&apos;ve saved these codes
            </button>
          </div>
        </div>
      )}

      {/* Not enabled, not enrolling → offer setup */}
      {!enabled && !setup && (
        <button className={t.btnPrimary} onClick={beginSetup} disabled={loading}>
          <Icon name="ShieldCheck" size={16} />
          {loading ? 'Preparing…' : 'Set up two-factor authentication'}
        </button>
      )}

      {/* Enrollment in progress */}
      {!enabled && setup && (
        <div className={t.enrollPanel}>
          <div className={t.enrollStep}>
            <span className={t.stepNum}>1</span>
            Scan this QR code with your authenticator app
          </div>
          {qrDataUrl && <img src={qrDataUrl} alt="MFA enrollment QR code" className={t.qr} />}
          <div className={t.manualEntry}>
            Can&apos;t scan? Enter this key manually: <code className={t.code}>{setup.secret}</code>
          </div>
          <div className={t.enrollStep}>
            <span className={t.stepNum}>2</span>
            Enter the 6-digit code the app shows
          </div>
          <div className={t.enrollActions}>
            <input
              aria-label="6-digit code from your authenticator app"
              type="text"
              className={t.codeInput}
              value={enrollCode}
              onChange={(e) => setEnrollCode(e.target.value)}
              placeholder="123 456"
              inputMode="numeric"
              autoComplete="one-time-code"
            />
            <button
              className={t.btnPrimary}
              onClick={confirmEnable}
              disabled={loading || enrollCode.trim().length < 6}
            >
              {loading ? 'Verifying…' : 'Verify & enable'}
            </button>
            <button className={t.btnGhost} onClick={cancelSetup}>Cancel</button>
          </div>
        </div>
      )}

      {/* Enabled → management */}
      {enabled && (
        <div className={t.managePanel}>
          <div className={t.manageHeading}>Manage</div>
          <p className={t.manageNote}>
            Both actions require a current code from your authenticator app. Disabling also
            needs your account password, and accepts a recovery code in place of the app code.
          </p>
          <div className={t.enrollActions}>
            <input
              aria-label="Current authenticator or recovery code"
              type="text"
              className={t.codeInput}
              value={manageCode}
              onChange={(e) => setManageCode(e.target.value)}
              placeholder="Current code"
              inputMode="numeric"
              autoComplete="one-time-code"
            />
            <button
              className={t.btnGhost}
              onClick={regenerateCodes}
              disabled={loading || manageCode.trim().length < 6}
            >
              <Icon name="RefreshCw" size={14} /> New recovery codes
            </button>
            <input
              aria-label="Account password (needed to disable two-factor)"
              type="password"
              className={t.codeInput}
              value={managePassword}
              onChange={(e) => setManagePassword(e.target.value)}
              placeholder="Password (to disable)"
              autoComplete="current-password"
            />
            <button
              className={t.btnDanger}
              onClick={disable}
              disabled={loading || manageCode.trim().length < 6}
            >
              <Icon name="ShieldOff" size={14} /> Disable
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
