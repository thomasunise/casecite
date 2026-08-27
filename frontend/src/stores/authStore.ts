import { create } from 'zustand';
import { api } from '../api';
import { useUIStore } from './uiStore';
import { resetAllStores } from './resetRegistry';
import type { UserInfo } from '../api/types';

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
    if (state.signupPassword.length < 12) {
      set({ signupError: 'Password must be at least 12 characters', signupLoading: false });
      return;
    }
    if (!/[A-Z]/.test(state.signupPassword) || !/[a-z]/.test(state.signupPassword) ||
        !/\d/.test(state.signupPassword) || !/[^A-Za-z0-9]/.test(state.signupPassword)) {
      set({ signupError: 'Password must include uppercase, lowercase, number, and special character', signupLoading: false });
      return;
    }
    if (state.signupPassword !== state.signupConfirmPassword) {
      set({ signupError: 'Passwords do not match', signupLoading: false });
      return;
    }
    try {
      const result = await api.register(
        state.signupEmail.trim(),
        state.signupName.trim(),
        state.signupPassword,
        state.signupCompany.trim(),
      );

      set({
        user: result.user,
        isAuthenticated: true,
        showSignupModal: false,
        signupName: '', signupEmail: '', signupPassword: '',
        signupConfirmPassword: '', signupCompany: '',
      });
      addToast('Account created.', 'success');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Signup failed. Please try again.';
      set({ signupError: message });
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
    // Purge locally-cached confidential work product (the negotiating playbook
    // and practice profile live in wl_rag_settings) so it doesn't linger on a
    // shared machine after sign-out. The server remains the source of truth.
    try {
      localStorage.removeItem('wl_rag_settings');
    } catch { /* storage unavailable — nothing to clear */ }
    // Every store holding this user's work (research, contracts, drafts,
    // judge intel, open document blobs…) goes back to its initial state so
    // the next sign-in on a shared workstation starts clean.
    resetAllStores();
    set({
      user: null, isAuthenticated: false,
      loginEmail: '', loginPassword: '', loginError: '',
    });
    addToast('Signed out', 'info');
  },
}));
