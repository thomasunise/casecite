import { useEffect, useId, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { useAuthStore } from '../stores/authStore';
import { PASSWORD_POLICY_HINT, validateNewPassword } from '../utils/passwordPolicy';
import { Icon } from '../components/shared/Icon';
import s from './ResetPasswordView.module.css';

type Stage = 'checking' | 'invalid' | 'form' | 'done';

/**
 * Landing page for the emailed password-reset link
 * (`/reset-password?token=…`). Reachable signed out. Verifies the token,
 * collects a new password, and hands off to the sign-in dialog.
 */
function ResetPasswordView() {
  const id = useId();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';

  const [stage, setStage] = useState<Stage>(token ? 'checking' : 'invalid');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) { setStage('invalid'); return; }
    let cancelled = false;
    setStage('checking');
    api.verifyResetToken(token)
      .then((res) => { if (!cancelled) setStage(res.valid ? 'form' : 'invalid'); })
      .catch(() => { if (!cancelled) setStage('invalid'); });
    return () => { cancelled = true; };
  }, [token]);

  const submit = async () => {
    const problem = validateNewPassword(password, confirm);
    if (problem) { setError(problem); return; }
    setSubmitting(true);
    setError('');
    try {
      await api.resetPassword(token, password);
      // A reset revokes every session server-side; make this device agree.
      if (useAuthStore.getState().isAuthenticated) useAuthStore.getState().clearSession();
      setPassword('');
      setConfirm('');
      setStage('done');
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Could not reset your password';
      // The link is single-use and short-lived — once the server rejects the
      // token there is nothing left to retry on this page.
      if (/invalid or expired/i.test(message)) setStage('invalid');
      else setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const goToSignIn = () => {
    navigate('/research', { replace: true });
    useAuthStore.getState().handleLogin();
  };

  const requestNewLink = () => {
    navigate('/research', { replace: true });
    const auth = useAuthStore.getState();
    auth.setForgotSuccess(false);
    auth.setShowForgotPassword(true);
  };

  return (
    <div className={s.page}>
      <div className={s.card}>
        <div className={s.iconCircle}>
          <Icon name={stage === 'done' ? 'Check' : 'KeyRound'} size={28} className={s.icon} />
        </div>

        {stage === 'checking' && (
          <>
            <h2 className={s.heading}>Checking your reset link…</h2>
            <p className={s.text} role="status">One moment.</p>
          </>
        )}

        {stage === 'invalid' && (
          <>
            <h2 className={s.heading}>This reset link can&apos;t be used</h2>
            <p className={s.text}>
              Reset links work once and expire after an hour. Request a new one and use it right away.
            </p>
            <div className={s.actions}>
              <button type="button" className={s.primaryButton} onClick={requestNewLink}>Request a new link</button>
              <button type="button" className={s.secondaryButton} onClick={goToSignIn}>Back to sign in</button>
            </div>
          </>
        )}

        {stage === 'form' && (
          <>
            <h2 className={s.heading}>Choose a new password</h2>
            <form className={s.form} onSubmit={e => { e.preventDefault(); submit(); }}>
              {error && <div className={s.errorBox} role="alert">{error}</div>}
              <div>
                <label htmlFor={`${id}-new`} className={s.label}>New password</label>
                <input id={`${id}-new`} type="password" className={s.input} value={password}
                  onChange={e => setPassword(e.target.value)} autoComplete="new-password"
                  aria-describedby={`${id}-policy`} autoFocus />
                <p id={`${id}-policy`} className={s.hint}>{PASSWORD_POLICY_HINT}</p>
              </div>
              <div>
                <label htmlFor={`${id}-confirm`} className={s.label}>Confirm new password</label>
                <input id={`${id}-confirm`} type="password" className={s.input} value={confirm}
                  onChange={e => setConfirm(e.target.value)} autoComplete="new-password" />
              </div>
              <button type="submit" className={s.primaryButton} disabled={submitting}>
                {submitting ? 'Saving…' : 'Reset password'}
              </button>
            </form>
          </>
        )}

        {stage === 'done' && (
          <>
            <h2 className={s.heading}>Password updated</h2>
            <p className={s.text}>
              You&apos;ve been signed out everywhere. Sign in with your new password to continue.
            </p>
            <div className={s.actions}>
              <button type="button" className={s.primaryButton} onClick={goToSignIn}>Sign in</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default ResetPasswordView;
