import { useId } from 'react';
import { useAuthStore } from '../../stores/authStore';
import s from './AuthModals.module.css';
import { Icon } from '../shared/Icon';
import { ModalShell } from '../shared/ModalShell';

function SignupModal() {
  const id = useId();
  const {
    showSignupModal, setShowSignupModal,
    signupName, setSignupName, signupEmail, setSignupEmail,
    signupPassword, setSignupPassword, signupConfirmPassword, setSignupConfirmPassword,
    signupCompany, setSignupCompany,
    signupBootstrapToken, setSignupBootstrapToken, signupNeedsBootstrapToken,
    signupError, signupLoading,
    handleSignupSubmit, handleShowLogin,
  } = useAuthStore();

  if (!showSignupModal) return null;

  return (
    <ModalShell onClose={() => setShowSignupModal(false)} overlayClassName={s.modalOverlay} className={s.modalContainerMedium} labelledBy={`${id}-title`}>
        <div className={s.modalHeader}>
          <div className={s.modalHeaderLeft}>
            <div className={s.modalIconNavy}>
              <Icon name="UserPlus" size={20} style={{color: 'var(--on-secondary)'}} />
            </div>
            <div>
              <h2 id={`${id}-title`} className={s.modalTitle}>Register</h2>
              <p className={s.modalSubtitle}>Create your account</p>
            </div>
          </div>
          <button className={s.modalClose} onClick={() => setShowSignupModal(false)} aria-label="Close"><Icon name="X" size={20} /></button>
        </div>
        <div className={s.modalBody}>
          {signupError && (
            <div className={s.errorBox}>
              {signupError}
            </div>
          )}
          <form id={`${id}-form`} onSubmit={e => { e.preventDefault(); handleSignupSubmit(); }} className={s.formLayout}>
            <div>
              <label htmlFor={`${id}-name`} className={s.formLabel}>Full Name *</label>
              <input id={`${id}-name`} type="text" className={s.modalInput} value={signupName} onChange={e => setSignupName(e.target.value)}
                placeholder="John Smith" autoComplete="name" />
            </div>
            <div>
              <label htmlFor={`${id}-email`} className={s.formLabel}>Work Email *</label>
              <input id={`${id}-email`} type="email" className={s.modalInput} value={signupEmail} onChange={e => setSignupEmail(e.target.value)}
                placeholder="john@lawfirm.com" autoComplete="email" />
            </div>
            <div>
              <label htmlFor={`${id}-company`} className={s.formLabel}>Company/Firm</label>
              <input id={`${id}-company`} type="text" className={s.modalInput} value={signupCompany} onChange={e => setSignupCompany(e.target.value)}
                placeholder="Smith & Associates" autoComplete="organization" />
            </div>
            <div>
              <label htmlFor={`${id}-password`} className={s.formLabel}>Password *</label>
              <input id={`${id}-password`} type="password" className={s.modalInput} value={signupPassword} onChange={e => setSignupPassword(e.target.value)}
                placeholder="12+ characters with upper, lower, number & symbol" autoComplete="new-password" />
            </div>
            <div>
              <label htmlFor={`${id}-confirm`} className={s.formLabel}>Confirm Password *</label>
              <input id={`${id}-confirm`} type="password" className={s.modalInput} value={signupConfirmPassword} onChange={e => setSignupConfirmPassword(e.target.value)}
                placeholder="Confirm your password" autoComplete="new-password" />
            </div>
            {/* Only the very first account on a new instance needs this. It
                opens by itself when the server asks for the token. */}
            <details className={s.setupDisclosure} open={signupNeedsBootstrapToken || undefined}>
              <summary>Initial setup — creating the first administrator</summary>
              <label htmlFor={`${id}-setup-token`} className={s.formLabel}>Setup token</label>
              <input id={`${id}-setup-token`} type="password" className={s.modalInput} value={signupBootstrapToken}
                onChange={e => setSignupBootstrapToken(e.target.value)} autoComplete="off"
                aria-describedby={`${id}-setup-hint`} />
              <p id={`${id}-setup-hint`} className={s.policyHint}>
                The value of REGISTRATION_BOOTSTRAP_TOKEN from this server&apos;s configuration. The first
                account becomes the administrator. Leave it empty for every later registration.
              </p>
            </details>
          </form>
        </div>
        <div className={s.modalFooter}>
          <button type="button" className={s.btnSecondary} onClick={() => setShowSignupModal(false)}>Cancel</button>
          <button type="submit" form={`${id}-form`} className={s.btnPrimary} disabled={signupLoading}>
            {signupLoading ? 'Creating account...' : 'Register'}
          </button>
        </div>
        <div className={s.bottomBar}>
          Already have an account?{' '}
          <button type="button" onClick={handleShowLogin} className={s.switchLink}>
            Sign in
          </button>
        </div>
    </ModalShell>
  );
}

export { SignupModal };
