import { useEffect } from 'react';
import { useMfaStore } from '../../../stores/mfaStore';
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
    manageCode, setManageCode,
    loadStatus, beginSetup, cancelSetup, confirmEnable, disable, regenerateCodes,
  } = useMfaStore();

  useEffect(() => { loadStatus(); }, [loadStatus]);

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
            Both actions require a current code from your authenticator app.
            Disabling also accepts a recovery code.
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
