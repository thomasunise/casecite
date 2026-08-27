import { useId } from 'react';
import { useAuthStore } from '../../stores/authStore';
import s from './AuthModals.module.css';
import { Icon } from '../shared/Icon';
import { ModalShell } from '../shared/ModalShell';

function ForgotPasswordModal() {
  const id = useId();
  const {
    showForgotPassword, setShowForgotPassword,
    forgotEmail, setForgotEmail,
    forgotLoading, forgotSuccess,
    handleForgotPassword, setShowLoginModal,
  } = useAuthStore();

  if (!showForgotPassword) return null;

  return (
    <ModalShell onClose={() => setShowForgotPassword(false)} overlayClassName={s.modalOverlay} className={s.modalContainerSmall} labelledBy={`${id}-title`}>
        <div className={s.modalHeader}>
          <div className={s.modalHeaderLeft}>
            <div className={s.modalIconAmber}>
              <Icon name="Key" size={20} style={{color: 'white'}} />
            </div>
            <div>
              <h2 id={`${id}-title`} className={s.modalTitle}>Reset Password</h2>
              <p className={s.modalSubtitle}>We'll send you a reset link</p>
            </div>
          </div>
          <button className={s.modalClose} onClick={() => setShowForgotPassword(false)} aria-label="Close"><Icon name="X" size={20} /></button>
        </div>
        <div className={s.modalBody}>
          {forgotSuccess ? (
            <div className={s.successContainer}>
              <div className={s.successIcon}>
                <Icon name="Mail" size={28} style={{ color: 'var(--green-600)' }} />
              </div>
              <h3 className={s.successTitle}>Check your email</h3>
              <p className={s.successMessage}>
                If an account exists for {forgotEmail}, you'll receive a password reset link shortly.
              </p>
            </div>
          ) : (
            <div className={s.formLayout}>
              <div>
                <label htmlFor={`${id}-email`} className={s.formLabel}>Email</label>
                <input id={`${id}-email`} type="email" className={s.modalInput} value={forgotEmail} onChange={e => setForgotEmail(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleForgotPassword()} placeholder="you@example.com" />
              </div>
            </div>
          )}
        </div>
        <div className={s.modalFooter}>
          {forgotSuccess ? (
            <button className={s.btnPrimary} onClick={() => { setShowForgotPassword(false); setShowLoginModal(true); }}>
              Back to Sign In
            </button>
          ) : (
            <>
              <button className={s.btnSecondary} onClick={() => { setShowForgotPassword(false); setShowLoginModal(true); }}>Back</button>
              <button className={s.btnPrimary} onClick={handleForgotPassword} disabled={forgotLoading || !forgotEmail.trim()}>
                {forgotLoading ? 'Sending...' : 'Send Reset Link'}
              </button>
            </>
          )}
        </div>
    </ModalShell>
  );
}

export { ForgotPasswordModal };
