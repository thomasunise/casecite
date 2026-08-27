import { api } from './client';
import type { AuthResponse, UserInfo, MessageResponse } from './types';

Object.assign(api, {
  async login(email: string, password: string): Promise<AuthResponse> {
    const result = await api.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    api.setToken(result.access_token);
    return result;
  },

  async refreshToken(): Promise<AuthResponse | null> {
    try {
      const result = await api.request('/auth/refresh', {
        method: 'POST',
        body: JSON.stringify({}),
      });
      return result as AuthResponse;
    } catch {
      return null;
    }
  },

  async logout(): Promise<void> {
    try { await api.request('/auth/logout', { method: 'POST' }); } catch {}
    // The refresh token lives in an httpOnly cookie the backend just cleared.
    api.token = null;
  },

  async getCurrentUser(): Promise<UserInfo> {
    return api.request('/auth/me');
  },

  async register(email: string, name: string, password: string, company: string): Promise<AuthResponse> {
    const result = await api.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, name, password, company }),
    });
    api.setToken(result.access_token);
    return result;
  },

  async forgotPassword(email: string): Promise<MessageResponse> {
    return api.request('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  },
});
