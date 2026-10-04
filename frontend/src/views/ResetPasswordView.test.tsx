import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../api', () => ({
  api: {
    token: null,
    verifyResetToken: vi.fn(),
    resetPassword: vi.fn(),
  },
  API_BASE_URL: 'http://localhost:8000/api/v1',
}));

vi.mock('../utils/logger', () => ({ default: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { api } from '../api';
import { useAuthStore } from '../stores/authStore';
import ResetPasswordView from './ResetPasswordView';

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <ResetPasswordView />
    </MemoryRouter>,
  );
}

function submitNewPassword(password: string, confirm = password) {
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: password } });
  fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: confirm } });
  fireEvent.click(screen.getByRole('button', { name: 'Reset password' }));
}

describe('ResetPasswordView', () => {
  beforeEach(() => {
    useAuthStore.setState(useAuthStore.getInitialState(), true);
    vi.clearAllMocks();
  });

  it('rejects a link with no token without calling the server', () => {
    renderAt('/reset-password');
    expect(screen.getByText("This reset link can't be used")).toBeInTheDocument();
    expect(api.verifyResetToken).not.toHaveBeenCalled();
  });

  it('shows the invalid state when the server does not recognise the token', async () => {
    (api.verifyResetToken as ReturnType<typeof vi.fn>).mockResolvedValue({ valid: false });
    renderAt('/reset-password?token=expired');
    expect(await screen.findByText("This reset link can't be used")).toBeInTheDocument();
    expect(api.verifyResetToken).toHaveBeenCalledWith('expired');
  });

  it('offers a new link from the invalid state', async () => {
    (api.verifyResetToken as ReturnType<typeof vi.fn>).mockResolvedValue({ valid: false });
    renderAt('/reset-password?token=expired');
    fireEvent.click(await screen.findByRole('button', { name: 'Request a new link' }));
    expect(useAuthStore.getState().showForgotPassword).toBe(true);
  });

  it('shows the password policy and blocks a weak password locally', async () => {
    (api.verifyResetToken as ReturnType<typeof vi.fn>).mockResolvedValue({ valid: true });
    renderAt('/reset-password?token=good');

    expect(await screen.findByText('Choose a new password')).toBeInTheDocument();
    expect(screen.getByText(/At least 12 characters/)).toBeInTheDocument();

    submitNewPassword('short');

    expect(screen.getByRole('alert')).toHaveTextContent('at least 12 characters');
    expect(api.resetPassword).not.toHaveBeenCalled();
  });

  it('resets the password and hands off to sign-in', async () => {
    (api.verifyResetToken as ReturnType<typeof vi.fn>).mockResolvedValue({ valid: true });
    (api.resetPassword as ReturnType<typeof vi.fn>).mockResolvedValue({ message: 'ok' });
    renderAt('/reset-password?token=good');
    await screen.findByText('Choose a new password');

    submitNewPassword('Brand-New-Pass-1!');

    expect(await screen.findByText('Password updated')).toBeInTheDocument();
    expect(api.resetPassword).toHaveBeenCalledWith('good', 'Brand-New-Pass-1!');

    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(useAuthStore.getState().showLoginModal).toBe(true);
  });

  it('falls back to the invalid state when the token expires between check and submit', async () => {
    (api.verifyResetToken as ReturnType<typeof vi.fn>).mockResolvedValue({ valid: true });
    (api.resetPassword as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Invalid or expired reset token'));
    renderAt('/reset-password?token=good');
    await screen.findByText('Choose a new password');

    submitNewPassword('Brand-New-Pass-1!');

    await waitFor(() => expect(screen.getByText("This reset link can't be used")).toBeInTheDocument());
  });

  it('shows a server-side policy error and keeps the form', async () => {
    (api.verifyResetToken as ReturnType<typeof vi.fn>).mockResolvedValue({ valid: true });
    (api.resetPassword as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Password was found in a breach list'));
    renderAt('/reset-password?token=good');
    await screen.findByText('Choose a new password');

    submitNewPassword('Brand-New-Pass-1!');

    expect(await screen.findByRole('alert')).toHaveTextContent('Password was found in a breach list');
    expect(screen.getByRole('button', { name: 'Reset password' })).toBeInTheDocument();
  });
});
