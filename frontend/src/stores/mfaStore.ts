import { create } from 'zustand';
import { registerReset } from './resetRegistry';
import { api } from '../api';
import { useUIStore } from './uiStore';
import { useAuthStore } from './authStore';
import type { MfaSetup } from '../api/types';

/**
 * MFA enrollment/management state for the settings Security tab.
 *
 * Flow: loadStatus → beginSetup (secret + otpauth URI for the QR) →
 * confirmEnable(code) (returns recovery codes, shown exactly once) →
 * later disable(code) or regenerateCodes(code).
 */
export interface MfaState {
  enabled: boolean;
  recoveryCodesRemaining: number;
  statusLoaded: boolean;
  loading: boolean;

  // Enrollment in progress
  setup: MfaSetup | null;
  qrDataUrl: string | null;
  enrollCode: string;
  setEnrollCode: (val: string) => void;

  // Recovery codes — held only until the user dismisses them
  freshRecoveryCodes: string[] | null;
  dismissRecoveryCodes: () => void;

  // Management code entry (disable / regenerate)
  manageCode: string;
  setManageCode: (val: string) => void;
  /** Account password — required (with a code) to turn two-factor off. */
  managePassword: string;
  setManagePassword: (val: string) => void;

  loadStatus: () => Promise<void>;
  beginSetup: () => Promise<void>;
  cancelSetup: () => void;
  confirmEnable: () => Promise<void>;
  disable: () => Promise<void>;
  regenerateCodes: () => Promise<void>;
}

export const useMfaStore = create<MfaState>((set, get) => ({
  enabled: false,
  recoveryCodesRemaining: 0,
  statusLoaded: false,
  loading: false,

  setup: null,
  qrDataUrl: null,
  enrollCode: '',
  setEnrollCode: (val) => set({ enrollCode: val }),

  freshRecoveryCodes: null,
  dismissRecoveryCodes: () => set({ freshRecoveryCodes: null }),

  manageCode: '',
  setManageCode: (val) => set({ manageCode: val }),
  managePassword: '',
  setManagePassword: (val) => set({ managePassword: val }),

  loadStatus: async () => {
    try {
      const status = await api.getMfaStatus();
      set({
        enabled: status.enabled,
        recoveryCodesRemaining: status.recovery_codes_remaining,
        statusLoaded: true,
      });
    } catch {
      set({ statusLoaded: false });
    }
  },

  beginSetup: async () => {
    const { addToast } = useUIStore.getState();
    set({ loading: true });
    try {
      const setup = await api.setupMfa();
      // Only the Security tab's enrollment step renders a QR — keep the
      // encoder out of the main bundle until then.
      const { default: QRCode } = await import('qrcode');
      const qrDataUrl = await QRCode.toDataURL(setup.provisioning_uri, { margin: 1, width: 220 });
      set({ setup, qrDataUrl, enrollCode: '' });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      addToast(`Could not start MFA setup: ${message}`, 'error');
    } finally {
      set({ loading: false });
    }
  },

  cancelSetup: () => set({ setup: null, qrDataUrl: null, enrollCode: '' }),

  confirmEnable: async () => {
    const { addToast } = useUIStore.getState();
    const { enrollCode } = get();
    set({ loading: true });
    try {
      const result = await api.enableMfa(enrollCode);
      set({
        setup: null,
        qrDataUrl: null,
        enrollCode: '',
        freshRecoveryCodes: result.recovery_codes,
      });
      addToast('Two-factor authentication enabled', 'success');
      await get().loadStatus();
      // Clears the "enrollment required" flag on the signed-in user.
      await useAuthStore.getState().refreshUser();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      addToast(message, 'error');
    } finally {
      set({ loading: false });
    }
  },

  disable: async () => {
    const { addToast, showConfirm } = useUIStore.getState();
    const { manageCode, managePassword } = get();
    showConfirm({
      title: 'Disable two-factor authentication',
      message: 'Your account will no longer require a second factor at sign-in. Continue?',
      type: 'warning',
      onConfirm: async () => {
        set({ loading: true });
        try {
          await api.disableMfa(manageCode, managePassword);
          set({ manageCode: '', managePassword: '', freshRecoveryCodes: null });
          addToast('Two-factor authentication disabled', 'info');
          await get().loadStatus();
          await useAuthStore.getState().refreshUser();
        } catch (error: unknown) {
          const message = error instanceof Error ? error.message : String(error);
          addToast(message, 'error');
        } finally {
          set({ loading: false });
        }
      },
    });
  },

  regenerateCodes: async () => {
    const { addToast } = useUIStore.getState();
    const { manageCode } = get();
    set({ loading: true });
    try {
      const result = await api.regenerateRecoveryCodes(manageCode);
      set({ manageCode: '', freshRecoveryCodes: result.recovery_codes });
      addToast('New recovery codes generated — previous codes no longer work', 'success');
      await get().loadStatus();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      addToast(message, 'error');
    } finally {
      set({ loading: false });
    }
  },
}));

// Secrets and recovery codes must not outlive the session that created them.
registerReset(() => useMfaStore.setState(useMfaStore.getInitialState(), true));
