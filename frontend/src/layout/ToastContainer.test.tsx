import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useUIStore, type Toast } from '../stores/uiStore';
import { ToastContainer } from './ToastContainer';

function setToasts(toasts: Toast[]) {
  useUIStore.setState({ toasts });
}

describe('ToastContainer', () => {
  beforeEach(() => {
    useUIStore.setState({ toasts: [] });
  });

  it('renders nothing when toasts array is empty', () => {
    const { container } = render(<ToastContainer />);
    const wrapper = container.querySelector('[data-layout="toasts"]');
    expect(wrapper!.children).toHaveLength(0);
  });

  it('renders a toast with the correct message', () => {
    setToasts([{ id: '1', message: 'Saved!', type: 'success' }]);
    render(<ToastContainer />);
    expect(screen.getByText('Saved!')).toBeInTheDocument();
  });

  it('renders multiple toasts', () => {
    setToasts([
      { id: '1', message: 'First', type: 'info' },
      { id: '2', message: 'Second', type: 'error' },
    ]);
    render(<ToastContainer />);
    expect(screen.getByText('First')).toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
  });

  it('applies success class for success type', () => {
    setToasts([{ id: '1', message: 'OK', type: 'success' }]);
    render(<ToastContainer />);
    const toast = screen.getByText('OK');
    expect(toast.className).toContain('toastSuccess');
  });

  it('applies error class for error type', () => {
    setToasts([{ id: '1', message: 'Fail', type: 'error' }]);
    render(<ToastContainer />);
    const toast = screen.getByText('Fail');
    expect(toast.className).toContain('toastError');
  });

  it('applies info class for info type', () => {
    setToasts([{ id: '1', message: 'Note', type: 'info' }]);
    render(<ToastContainer />);
    const toast = screen.getByText('Note');
    expect(toast.className).toContain('toastInfo');
  });
});
