import { api } from './client';
import type { AuthResponse, MfaRecoveryCodes, MfaSetup, MfaStatus } from './types';

Object.assign(api, {
  async getMfaStatus(): Promise<MfaStatus> {
    return api.request('/auth/mfa/status');
  },

  async setupMfa(): Promise<MfaSetup> {
    return api.request('/auth/mfa/setup', { method: 'POST' });
  },

  async enableMfa(code: string): Promise<MfaRecoveryCodes> {
    return api.request('/auth/mfa/enable', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
  },

  async disableMfa(code: string): Promise<{ status: string }> {
    return api.request('/auth/mfa/disable', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
  },

  async verifyMfa(mfaToken: string, code: string): Promise<AuthResponse> {
    return api.request('/auth/mfa/verify', {
      method: 'POST',
      body: JSON.stringify({ mfa_token: mfaToken, code }),
    });
  },

  async regenerateRecoveryCodes(code: string): Promise<MfaRecoveryCodes> {
    return api.request('/auth/mfa/recovery-codes', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
  },
});
