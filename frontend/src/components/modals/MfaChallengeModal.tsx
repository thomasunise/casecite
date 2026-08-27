import { useId } from 'react';
import { useAuthStore } from '../../stores/authStore';
import s from './AuthModals.module.css';
import { Icon } from '../shared/Icon';
import { ModalShell } from '../shared/ModalShell';

function MfaChallengeModal() {
  const id = useId();
  const {
    showMfaModal, mfaCode, setMfaCode, mfaError, mfaLoading,
    handleMfaVerifySubmit, cancelMfaChallenge,
  } = useAuthStore();

  if (!showMfaModal) return null;

  return (
    <ModalShell onClose={cancelMfaChallenge} overlayClassName={s.modalOverlay} className={s.modalContainerSmall} labelledBy={`${id}-title`}>
        <div className={s.modalHeader}>
          <div className={s.modalHeaderLeft}>
            <div className={s.modalIconNavy}>
              <Icon name="ShieldCheck" size={20} style={{ color: 'var(--on-secondary)' }} />
            </div>
            <div>
              <h2 id={`${id}-title`} className={s.modalTitle}>Two-Factor Verification</h2>
              <p className={s.modalSubtitle}>Enter the code from your authenticator app</p>
            </div>
          </div>
          <button className={s.modalClose} onClick={cancelMfaChallenge} aria-label="Close"><Icon name="X" size={20} /></button>
        </div>
        <div className={s.modalBody}>
          {mfaError && (
            <div className={s.errorBox}>{mfaError}</div>
          )}
          <form onSubmit={e => { e.preventDefault(); handleMfaVerifySubmit(); }} className={s.formLayout}>
            <div>
              <label htmlFor={`${id}-code`} className={s.formLabel}>Authentication code</label>
              <input
                id={`${id}-code`}
                type="text"
                className={s.modalInput}
                value={mfaCode}
                onChange={e => setMfaCode(e.target.value)}
                placeholder="6-digit code or recovery code"
                autoComplete="one-time-code"
                inputMode="numeric"
                autoFocus
              />
            </div>
          </form>
          <p className={s.modalSubtitle}>
            Lost your device? Enter one of your recovery codes instead.
          </p>
        </div>
        <div className={s.modalFooter}>
          <button className={s.btnSecondary} onClick={cancelMfaChallenge}>Cancel</button>
          <button className={s.btnPrimary} onClick={handleMfaVerifySubmit} disabled={mfaLoading || !mfaCode.trim()}>
            {mfaLoading ? 'Verifying...' : 'Verify'}
          </button>
        </div>
    </ModalShell>
  );
}

export { MfaChallengeModal };
