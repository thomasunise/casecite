import { useUIStore, type Toast } from '../stores/uiStore';
import s from './ToastContainer.module.css';

const toastTypeClass: Record<string, string> = {
  error: s.toastError,
  success: s.toastSuccess,
  info: s.toastInfo,
};

export function ToastContainer() {
  const toasts = useUIStore(s => s.toasts);

  return (
    <div data-layout="toasts" className={s.container} aria-live="polite" role="status">
      {toasts.map((toast: Toast) => (
        <div key={toast.id} className={`${s.toast} ${toastTypeClass[toast.type] || s.toastInfo}`}>
          {toast.message}
        </div>
      ))}
    </div>
  );
}
