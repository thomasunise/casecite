import { create } from 'zustand';
import { api } from '../api';
import { useUIStore } from './uiStore';
import { resetAllStores } from './resetRegistry';
import { clearStoredRagSettings } from '../utils/storageKeys';
import { validateNewPassword } from '../utils/passwordPolicy';
import type { UserInfo } from '../api/types';

/**
 * Drop everything that belongs to the signed-in user on this device: the
 * locally cached settings (the negotiating playbook and practice profile are
 * confidential work product) and every store holding their research,
 * contracts, drafts, judge intel or open document blobs — so the next
 * sign-in on a shared workstation starts clean.
 */
function clearLocalSession() {
  clearStoredRagSettings();
  resetAllStores();
}

export interface AuthState {
  // Core auth
  user: UserInfo | null;
  setUser: (user: UserInfo | null) => void;
  isAuthenticated: boolean;
  setIsAuthenticated: (val: boolean) => void;

  // Login modal
  showLoginModal: boolean;
  setShowLoginModal: (val: boolean) => void;
  loginEmail: string;
  setLoginEmail: (val: string) => void;
  loginPassword: string;
  setLoginPassword: (val: string) => void;
  loginError: string;
  loginLoading: boolean;

  // Signup modal
  showSignupModal: boolean;
  setShowSignupModal: (val: boolean) => void;
  signupName: string;
  setSignupName: (val: string) => void;
  signupEmail: string;
  setSignupEmail: (val: string) => void;
  signupPassword: string;
  setSignupPassword: (val: string) => void;
  signupConfirmPassword: string;
  setSignupConfirmPassword: (val: string) => void;
  signupCompany: string;
  setSignupCompany: (val: string) => void;
  /** REGISTRATION_BOOTSTRAP_TOKEN — needed only to create the first admin. */
  signupBootstrapToken: string;
  setSignupBootstrapToken: (val: string) => void;
  /** The server said the setup token is required (or the one given was wrong). */
  signupNeedsBootstrapToken: boolean;
  signupError: string;
  signupLoading: boolean;

  // Forgot password
  showForgotPassword: boolean;
  setShowForgotPassword: (val: boolean) => void;
  forgotEmail: string;
  setForgotEmail: (val: string) => void;
  forgotLoading: boolean;
  forgotSuccess: boolean;
  setForgotSuccess: (val: boolean) => void;

  // MFA second login step
  showMfaModal: boolean;
  mfaToken: string | null;
  mfaCode: string;
  setMfaCode: (val: string) => void;
  mfaError: string;
  mfaLoading: boolean;
  handleMfaVerifySubmit: () => Promise<void>;
  cancelMfaChallenge: () => void;

  // Change password (voluntary from Settings, or forced for an account still
  // on an admin-issued temporary password)
  showChangePassword: boolean;
  setShowChangePassword: (val: boolean) => void;
  changePasswordError: string;
  changePasswordLoading: boolean;
  /** Resolves true when the password was changed (the user is then signed out). */
  handleChangePassword: (currentPassword: string, newPassword: string, confirmPassword: string) => Promise<boolean>;

  /** Forget the session on this device without calling the server (it is already gone there). */
  clearSession: () => void;
  /** Re-read the signed-in user's flags (e.g. after enrolling in MFA). */
  refreshUser: () => Promise<void>;
  /** Revoke every session for this account, on every device, then sign out here. */
  handleLogoutEverywhere: () => Promise<void>;

  // Handlers
  handleLogin: () => void;
  handleShowSignup: () => void;
  handleShowLogin: () => void;
  handleSignupSubmit: () => Promise<void>;
  handleForgotPassword: () => Promise<void>;
  handleLoginSubmit: () => Promise<void>;
  handleLogout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  // Core auth state
  user: null,
  setUser: (user) => set({ user }),
  isAuthenticated: false,
  setIsAuthenticated: (val) => set({ isAuthenticated: val }),

  // Login modal state
  showLoginModal: false,
  setShowLoginModal: (val) => set({ showLoginModal: val }),
  loginEmail: '',
  setLoginEmail: (val) => set({ loginEmail: val }),
  loginPassword: '',
  setLoginPassword: (val) => set({ loginPassword: val }),
  loginError: '',
  loginLoading: false,

  // Signup modal state
  showSignupModal: false,
  setShowSignupModal: (val) => set({ showSignupModal: val }),
  signupName: '',
  setSignupName: (val) => set({ signupName: val }),
  signupEmail: '',
  setSignupEmail: (val) => set({ signupEmail: val }),
  signupPassword: '',
  setSignupPassword: (val) => set({ signupPassword: val }),
  signupConfirmPassword: '',
  setSignupConfirmPassword: (val) => set({ signupConfirmPassword: val }),
  signupCompany: '',
  setSignupCompany: (val) => set({ signupCompany: val }),
  signupBootstrapToken: '',
  setSignupBootstrapToken: (val) => set({ signupBootstrapToken: val }),
  signupNeedsBootstrapToken: false,
  signupError: '',
  signupLoading: false,

  // Forgot password state
  showForgotPassword: false,
  setShowForgotPassword: (val) => set({ showForgotPassword: val }),
  forgotEmail: '',
  setForgotEmail: (val) => set({ forgotEmail: val }),
  forgotLoading: false,
  forgotSuccess: false,
  setForgotSuccess: (val) => set({ forgotSuccess: val }),

  // MFA second login step state
  showMfaModal: false,
  mfaToken: null,
  mfaCode: '',
  setMfaCode: (val) => set({ mfaCode: val }),
  mfaError: '',
  mfaLoading: false,

  // Change password state
  showChangePassword: false,
  setShowChangePassword: (val) => set({ showChangePassword: val, changePasswordError: '' }),
  changePasswordError: '',
  changePasswordLoading: false,

  handleChangePassword: async (currentPassword, newPassword, confirmPassword) => {
    const { addToast } = useUIStore.getState();
    if (!currentPassword) {
      set({ changePasswordError: 'Enter your current password' });
      return false;
    }
    const problem = validateNewPassword(newPassword, confirmPassword);
    if (problem) {
      set({ changePasswordError: problem });
      return false;
    }
    if (newPassword === currentPassword) {
      set({ changePasswordError: 'Choose a password different from your current one' });
      return false;
    }
    set({ changePasswordLoading: true, changePasswordError: '' });
    try {
      await api.changePassword(currentPassword, newPassword);
      // The server revokes every session on a password change (this one
      // included) — sign in again with the new password.
      const email = get().user?.email ?? '';
      api.token = null;
      clearLocalSession();
      set({
        user: null, isAuthenticated: false,
        showChangePassword: false,
        showLoginModal: true, loginEmail: email, loginPassword: '', loginError: '',
      });
      addToast('Password changed. Sign in with your new password.', 'success');
      return true;
    } catch (error: unknown) {
      set({ changePasswordError: error instanceof Error ? error.message : 'Could not change your password' });
      return false;
    } finally {
      set({ changePasswordLoading: false });
    }
  },

  clearSession: () => {
    api.token = null;
    clearLocalSession();
    set({ user: null, isAuthenticated: false, showChangePassword: false });
  },

  refreshUser: async () => {
    try {
      const user = await api.getCurrentUser();
      set({ user });
    } catch { /* the 401 path in api.request already handles a dead session */ }
  },

  handleLogoutEverywhere: async () => {
    const { addToast } = useUIStore.getState();
    try {
      await api.logoutAllSessions();
    } catch (error: unknown) {
      addToast(error instanceof Error ? error.message : 'Could not sign out your other sessions', 'error');
      return;
    }
    clearLocalSession();
    set({
      user: null, isAuthenticated: false,
      loginEmail: '', loginPassword: '', loginError: '',
    });
    addToast('Signed out on every device', 'info');
  },

  // Handlers
  handleLogin: () => {
    set({ showLoginModal: true, loginError: '' });
  },

  handleShowSignup: () => {
    set({ showLoginModal: false, showSignupModal: true, signupError: '' });
  },

  handleShowLogin: () => {
    set({ showSignupModal: false, showLoginModal: true, loginError: '' });
  },

  handleSignupSubmit: async () => {
    const state = get();
    const { addToast } = useUIStore.getState();
    set({ signupLoading: true, signupError: '' });

    if (!state.signupName.trim()) {
      set({ signupError: 'Please enter your name', signupLoading: false });
      return;
    }
    if (!state.signupEmail.trim()) {
      set({ signupError: 'Please enter your email', signupLoading: false });
      return;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(state.signupEmail.trim())) {
      set({ signupError: 'Please enter a valid email address', signupLoading: false });
      return;
    }
    const passwordProblem = validateNewPassword(state.signupPassword, state.signupConfirmPassword);
    if (passwordProblem) {
      set({ signupError: passwordProblem, signupLoading: false });
      return;
    }
    try {
      const result = await api.register(
        state.signupEmail.trim(),
        state.signupName.trim(),
        state.signupPassword,
        state.signupCompany.trim(),
        state.signupBootstrapToken.trim() || undefined,
      );

      set({
        user: result.user,
        isAuthenticated: true,
        showSignupModal: false,
        signupName: '', signupEmail: '', signupPassword: '',
        signupConfirmPassword: '', signupCompany: '',
        signupBootstrapToken: '', signupNeedsBootstrapToken: false,
      });
      addToast('Account created.', 'success');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Signup failed. Please try again.';
      // A fresh instance only lets its first (admin) account be created with
      // the operator's setup token — reveal the field when the server asks.
      set({ signupError: message, ...(/bootstrap token/i.test(message) ? { signupNeedsBootstrapToken: true } : {}) });
    } finally {
      set({ signupLoading: false });
    }
  },

  handleForgotPassword: async () => {
    const { forgotEmail } = get();
    set({ forgotLoading: true });
    try {
      await api.forgotPassword(forgotEmail);
      set({ forgotSuccess: true });
    } catch {
      // Always show success to prevent email enumeration
      set({ forgotSuccess: true });
    } finally {
      set({ forgotLoading: false });
    }
  },

  handleLoginSubmit: async () => {
    const state = get();
    const { addToast } = useUIStore.getState();
    set({ loginLoading: true, loginError: '' });
    try {
      const result = await api.login(state.loginEmail, state.loginPassword);
      if (result.mfa_required && result.mfa_token) {
        // Password accepted; a second factor is required before any tokens
        // exist. The password has done its job — don't keep it in memory
        // while the challenge is pending.
        set({
          showLoginModal: false,
          showMfaModal: true,
          mfaToken: result.mfa_token,
          mfaCode: '',
          mfaError: '',
          loginPassword: '',
        });
        return;
      }
      set({
        user: result.user,
        isAuthenticated: true,
        showLoginModal: false,
        loginEmail: '',
        loginPassword: '',
      });
      addToast('Signed in successfully', 'success');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Login failed';
      set({ loginError: message });
    } finally {
      set({ loginLoading: false });
    }
  },

  handleMfaVerifySubmit: async () => {
    const state = get();
    const { addToast } = useUIStore.getState();
    if (!state.mfaToken) return;
    set({ mfaLoading: true, mfaError: '' });
    try {
      const result = await api.verifyMfa(state.mfaToken, state.mfaCode);
      set({
        user: result.user,
        isAuthenticated: true,
        showMfaModal: false,
        mfaToken: null,
        mfaCode: '',
        loginEmail: '',
        loginPassword: '',
      });
      addToast('Signed in successfully', 'success');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Verification failed';
      // An expired challenge means the whole login must restart.
      if (message.toLowerCase().includes('expired')) {
        set({ showMfaModal: false, mfaToken: null, mfaCode: '', showLoginModal: true, loginError: message });
      } else {
        set({ mfaError: message });
      }
    } finally {
      set({ mfaLoading: false });
    }
  },

  cancelMfaChallenge: () => {
    set({
      showMfaModal: false, mfaToken: null, mfaCode: '', mfaError: '',
      loginEmail: '', loginPassword: '',
    });
  },

  handleLogout: async () => {
    const { addToast } = useUIStore.getState();
    await api.logout();
    clearLocalSession();
    set({
      user: null, isAuthenticated: false, showChangePassword: false,
      loginEmail: '', loginPassword: '', loginError: '',
    });
    addToast('Signed out', 'info');
  },
}));
