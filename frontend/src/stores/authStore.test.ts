import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../api', () => ({
  api: {
    login: vi.fn(),
    verifyMfa: vi.fn(),
    logout: vi.fn().mockResolvedValue(undefined),
    register: vi.fn(),
    forgotPassword: vi.fn(),
  },
  API_BASE_URL: 'http://localhost:8000/api/v1',
}));

vi.mock('../utils/logger', () => ({ default: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() } }));

import { useAuthStore } from './authStore';
import { useUIStore } from './uiStore';
import { useDraftingStore } from './draftingStore';
import { useContractsStore } from './contractsStore';
import { useMfaStore } from './mfaStore';
import { api } from '../api';

const user = { id: 'u1', email: 'a@b.c', roles: ['user'] };

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.setState(useAuthStore.getInitialState(), true);
    useUIStore.setState(useUIStore.getInitialState(), true);
    vi.clearAllMocks();
  });

  it('clears the typed credentials once login succeeds', async () => {
    (api.login as ReturnType<typeof vi.fn>).mockResolvedValue({ access_token: 't', user });
    useAuthStore.setState({ loginEmail: 'a@b.c', loginPassword: 'hunter2hunter2!A' });

    await useAuthStore.getState().handleLoginSubmit();

    const st = useAuthStore.getState();
    expect(st.isAuthenticated).toBe(true);
    expect(st.loginEmail).toBe('');
    expect(st.loginPassword).toBe('');
  });

  it('keeps the email but drops the password while an MFA challenge is pending', async () => {
    (api.login as ReturnType<typeof vi.fn>).mockResolvedValue({ mfa_required: true, mfa_token: 'mfa-1', user });
    useAuthStore.setState({ loginEmail: 'a@b.c', loginPassword: 'hunter2hunter2!A' });

    await useAuthStore.getState().handleLoginSubmit();

    const st = useAuthStore.getState();
    expect(st.showMfaModal).toBe(true);
    expect(st.loginPassword).toBe('');
  });

  it('clears the credentials after MFA verification succeeds', async () => {
    (api.verifyMfa as ReturnType<typeof vi.fn>).mockResolvedValue({ access_token: 't', user });
    useAuthStore.setState({ loginEmail: 'a@b.c', loginPassword: 'x', mfaToken: 'mfa-1', mfaCode: '123456', showMfaModal: true });

    await useAuthStore.getState().handleMfaVerifySubmit();

    const st = useAuthStore.getState();
    expect(st.isAuthenticated).toBe(true);
    expect(st.loginEmail).toBe('');
    expect(st.loginPassword).toBe('');
    expect(st.mfaToken).toBeNull();
  });

  it('cancelMfaChallenge clears the challenge and the credentials', () => {
    useAuthStore.setState({ loginEmail: 'a@b.c', loginPassword: 'x', mfaToken: 'mfa-1', showMfaModal: true });

    useAuthStore.getState().cancelMfaChallenge();

    const st = useAuthStore.getState();
    expect(st.showMfaModal).toBe(false);
    expect(st.mfaToken).toBeNull();
    expect(st.loginEmail).toBe('');
    expect(st.loginPassword).toBe('');
  });

  it('surfaces the server message when login fails', async () => {
    (api.login as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('Invalid email or password'));
    useAuthStore.setState({ loginEmail: 'a@b.c', loginPassword: 'wrong' });

    await useAuthStore.getState().handleLoginSubmit();

    expect(useAuthStore.getState().loginError).toBe('Invalid email or password');
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it('logout resets the other stores so the next user starts clean', async () => {
    useAuthStore.setState({ user, isAuthenticated: true, loginEmail: 'a@b.c' });
    useDraftingStore.setState({
      messages: [{ id: 'm1', role: 'user', text: 'Draft me an NDA' }],
      draftWorkspace: { title: 'NDA', text: 'Confidential…', dirty: true },
    });
    useContractsStore.setState({
      selectedDocumentId: 'doc-1',
      messages: [{ id: 'c1', role: 'user', kind: 'text', text: 'Review this' }],
    });
    useMfaStore.setState({ freshRecoveryCodes: ['aaaa-bbbb'], setup: { secret: 's', provisioning_uri: 'otpauth://x' } });

    await useAuthStore.getState().handleLogout();

    expect(api.logout).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().loginEmail).toBe('');

    expect(useDraftingStore.getState().messages).toEqual([]);
    expect(useDraftingStore.getState().draftWorkspace).toBeNull();
    expect(useContractsStore.getState().selectedDocumentId).toBe('');
    expect(useContractsStore.getState().messages).toEqual([]);
    expect(useMfaStore.getState().freshRecoveryCodes).toBeNull();
    expect(useMfaStore.getState().setup).toBeNull();

    // The stores still work after a full-state replace.
    useDraftingStore.getState().setTargetPages(5);
    expect(useDraftingStore.getState().targetPages).toBe(5);
    expect(useUIStore.getState().toasts.some(t => t.message === 'Signed out')).toBe(true);
  });
});
