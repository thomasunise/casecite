import { api } from './client';
import type { AdminUser, InviteUserResult, RolePermissionsMatrix } from './types';

Object.assign(api, {
  async getUsers(): Promise<{ users: AdminUser[] }> {
    return api.request('/admin/users');
  },

  async inviteUser(email: string, name: string, role: string): Promise<InviteUserResult> {
    return api.request('/admin/users/invite', {
      method: 'POST',
      body: JSON.stringify({ email, name, role }),
    });
  },

  async updateUserRole(userId: string, role: string): Promise<AdminUser> {
    return api.request(`/admin/users/${userId}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    });
  },

  async getRolePermissions(): Promise<RolePermissionsMatrix> {
    return api.request('/admin/users/roles');
  },

  async updateRolePermissions(role: string, permissions: string[]): Promise<RolePermissionsMatrix> {
    return api.request(`/admin/users/roles/${role}`, {
      method: 'PUT',
      body: JSON.stringify({ permissions }),
    });
  },

  async resetRolePermissions(): Promise<RolePermissionsMatrix> {
    return api.request('/admin/users/roles/reset', { method: 'POST' });
  },
});
