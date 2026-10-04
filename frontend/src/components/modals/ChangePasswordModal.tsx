import { useEffect, useId, useState } from 'react';
import { useAuthStore } from '../../stores/authStore';
import { PASSWORD_POLICY_HINT } from '../../utils/passwordPolicy';
import s from './AuthModals.module.css';
import { Icon } from '../shared/Icon';
import { ModalShell } from '../shared/ModalShell';

/**
 * Change the signed-in user's password.
 *
 * Opens on request from Settings → Security, and opens by itself — with no
 * way to dismiss it other than signing out — while the account is still on an
 * admin-issued temporary password (`must_change_password`). In that state the
 * API refuses everything except changing the password.
 */
function ChangePasswordModal() {
  const id = useId();
  const {
    user, isAuthenticated,
    showChangePassword, setShowChangePassword,
    changePasswordError, changePasswordLoading,
    handleChangePassword, handleLogout,
  } = useAuthStore();
  const forced = isAuthenticated && !!user?.must_change_password;
  const open = isAuthenticated && (forced || showChangePassword);

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');

  // Never keep typed passwords around once the dialog is gone.
  useEffect(() => {
    if (!open) { setCurrent(''); setNext(''); setConfirm(''); }
  }, [open]);

  if (!open) return null;

  const close = () => { if (!forced) setShowChangePassword(false); };
  const formId = `${id}-form`;

  return (
    <ModalShell
      onClose={close}
      closeOnBackdrop={!forced}
      closeOnEscape={!forced}
      overlayClassName={s.modalOverlay}
      className={s.modalContainerSmall}
      labelledBy={`${id}-title`}
    >
        <div className={s.modalHeader}>
          <div className={s.modalHeaderLeft}>
            <div className={s.modalIconNavy}>
              <Icon name="KeyRound" size={20} style={{ color: 'var(--on-secondary)' }} />
            </div>
            <div>
              <h2 id={`${id}-title`} className={s.modalTitle}>{forced ? 'Choose a New Password' : 'Change Password'}</h2>
              <p className={s.modalSubtitle}>
                {forced ? 'Your temporary password must be replaced before you continue' : 'You will be asked to sign in again afterwards'}
              </p>
            </div>
          </div>
          {!forced && (
            <button className={s.modalClose} onClick={close} aria-label="Close"><Icon name="X" size={20} /></button>
          )}
        </div>
        <div className={s.modalBody}>
          {changePasswordError && (
            <div className={s.errorBox} role="alert">{changePasswordError}</div>
          )}
          <form
            id={formId}
            onSubmit={e => { e.preventDefault(); handleChangePassword(current, next, confirm); }}
            className={s.formLayout}
          >
            <div>
              <label htmlFor={`${id}-current`} className={s.formLabel}>{forced ? 'Temporary password' : 'Current password'}</label>
              <input id={`${id}-current`} type="password" className={s.modalInput} value={current} onChange={e => setCurrent(e.target.value)}
                autoComplete="current-password" autoFocus />
            </div>
            <div>
              <label htmlFor={`${id}-new`} className={s.formLabel}>New password</label>
              <input id={`${id}-new`} type="password" className={s.modalInput} value={next} onChange={e => setNext(e.target.value)}
                autoComplete="new-password" aria-describedby={`${id}-policy`} />
              <p id={`${id}-policy`} className={s.policyHint}>{PASSWORD_POLICY_HINT}</p>
            </div>
            <div>
              <label htmlFor={`${id}-confirm`} className={s.formLabel}>Confirm new password</label>
              <input id={`${id}-confirm`} type="password" className={s.modalInput} value={confirm} onChange={e => setConfirm(e.target.value)}
                autoComplete="new-password" />
            </div>
          </form>
        </div>
        <div className={s.modalFooter}>
          {forced ? (
            <button type="button" className={s.btnSecondary} onClick={handleLogout}>Sign out</button>
          ) : (
            <button type="button" className={s.btnSecondary} onClick={close}>Cancel</button>
          )}
          <button type="submit" form={formId} className={s.btnPrimary} disabled={changePasswordLoading}>
            {changePasswordLoading ? 'Saving...' : 'Change Password'}
          </button>
        </div>
    </ModalShell>
  );
}

export { ChangePasswordModal };
