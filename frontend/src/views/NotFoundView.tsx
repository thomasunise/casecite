import { useNavigate } from 'react-router-dom';
import { Icon } from '../components/shared/Icon';
import s from './ResetPasswordView.module.css';

/** Shown for any path the app does not serve, instead of a silent redirect. */
function NotFoundView() {
  const navigate = useNavigate();
  return (
    <div className={s.page}>
      <div className={s.card}>
        <div className={s.iconCircle}>
          <Icon name="FileSearch" size={28} className={s.icon} />
        </div>
        <h2 className={s.heading}>Page not found</h2>
        <p className={s.text}>
          There is nothing at this address. The link may be out of date, or the page may have moved.
        </p>
        <div className={s.actions}>
          <button type="button" className={s.primaryButton} onClick={() => navigate('/research', { replace: true })}>
            Go to Matter Strategy
          </button>
        </div>
      </div>
    </div>
  );
}

export default NotFoundView;
