import { useState, useEffect, useCallback, useId } from 'react';
import { api } from '../../../api';
import { useUIStore } from '../../../stores/uiStore';
import { useAuthStore } from '../../../stores/authStore';
import { Icon } from '../../shared/Icon';
import type { AdminUser, RolePermissionsMatrix } from '../../../api/types';

interface UsersTabProps {
  s: Record<string, string>;
}

const ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'attorney', label: 'Attorney' },
  { value: 'paralegal', label: 'Paralegal' },
  { value: 'viewer', label: 'Viewer' },
] as const;

export const UsersTab = ({ s }: UsersTabProps) => {
  const id = useId();
  const addToast = useUIStore((st) => st.addToast);
  const showConfirm = useUIStore((st) => st.showConfirm);
  const currentUserId = useAuthStore((st) => st.user?.id);

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [matrix, setMatrix] = useState<RolePermissionsMatrix | null>(null);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteRole, setInviteRole] = useState('attorney');
  const [inviting, setInviting] = useState(false);
  const [tempPassword, setTempPassword] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.getUsers();
      setUsers(res.users);
    } catch (e) {
      addToast(e instanceof Error ? e.message : 'Failed to load users', 'error');
    }
    try {
      setMatrix(await api.getRolePermissions());
    } catch (e) {
      addToast(e instanceof Error ? e.message : 'Failed to load role permissions', 'error');
    }
  }, [addToast]);

  useEffect(() => { load(); }, [load]);

  const isLocked = (role: string, key: string) =>
    (matrix?.locked[role] || []).includes(key);

  const handleTogglePermission = async (role: string, key: string) => {
    if (!matrix || isLocked(role, key)) return;
    const current = matrix.assigned[role] || [];
    const next = current.includes(key)
      ? current.filter(k => k !== key)
      : [...current, key];
    const prev = matrix;
    // Optimistic flip; the PUT response is server truth (incl. customized flags).
    setMatrix({ ...matrix, assigned: { ...matrix.assigned, [role]: next } });
    try {
      setMatrix(await api.updateRolePermissions(role, next));
    } catch (e) {
      setMatrix(prev);
      addToast(e instanceof Error ? e.message : 'Failed to update permissions', 'error');
    }
  };

  const handleResetRoles = () => {
    showConfirm({
      title: 'Reset role permissions?',
      message: 'Every role returns to the shipped defaults. Custom grants are removed.',
      confirmText: 'Reset',
      onConfirm: async () => {
        try {
          setMatrix(await api.resetRolePermissions());
          addToast('Role permissions reset to defaults', 'success');
        } catch (e) {
          addToast(e instanceof Error ? e.message : 'Failed to reset', 'error');
        }
      },
    });
  };

  const permissionGroups = matrix
    ? Array.from(new Set(matrix.permissions.map(p => p.group)))
    : [];

  const handleInvite = async () => {
    if (!inviteEmail.trim() || !inviteName.trim()) {
      addToast('Email and name are required', 'error');
      return;
    }
    setInviting(true);
    setTempPassword(null);
    try {
      const res = await api.inviteUser(inviteEmail.trim(), inviteName.trim(), inviteRole);
      setTempPassword(res.temporary_password);
      setInviteEmail('');
      setInviteName('');
      setInviteRole('attorney');
      addToast(`Invited ${res.user.email}`, 'success');
      await load();
    } catch (e) {
      addToast(e instanceof Error ? e.message : 'Failed to invite user', 'error');
    }
    setInviting(false);
  };

  const handleRoleChange = async (user: AdminUser, role: string) => {
    const prev = users;
    setUsers(users.map(u => (u.id === user.id ? { ...u, roles: [role] } : u)));
    try {
      await api.updateUserRole(user.id, role);
      addToast(`${user.email} is now ${role}`, 'success');
    } catch (e) {
      setUsers(prev); // revert on failure
      addToast(e instanceof Error ? e.message : 'Failed to update role', 'error');
    }
  };

  const copyTempPassword = () => {
    if (tempPassword) {
      navigator.clipboard?.writeText(tempPassword);
      addToast('Temporary password copied', 'success');
    }
  };

  return (
    <div className={s.usersTabContent}>
      {/* Invite */}
      <div className={s.inviteCard}>
        <div className={s.keyStatusTitle}>Invite a User</div>
        <div className={s.inviteRow}>
          <div className={s.inviteField}>
            <label className={s.settingLabel} htmlFor={`${id}-invite-email`}>Email</label>
            <input
              id={`${id}-invite-email`}
              className={s.modalInput}
              type="email"
              value={inviteEmail}
              onChange={e => setInviteEmail(e.target.value)}
              placeholder="name@firm.com"
            />
          </div>
          <div className={s.inviteField}>
            <label className={s.settingLabel} htmlFor={`${id}-invite-name`}>Name</label>
            <input
              id={`${id}-invite-name`}
              className={s.modalInput}
              value={inviteName}
              onChange={e => setInviteName(e.target.value)}
              placeholder="Full name"
            />
          </div>
          <div className={s.inviteField}>
            <label className={s.settingLabel} htmlFor={`${id}-invite-role`}>Role</label>
            <select id={`${id}-invite-role`} className={s.select} value={inviteRole} onChange={e => setInviteRole(e.target.value)}>
              {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </div>
          <button className={s.btnPrimary} onClick={handleInvite} disabled={inviting}>
            <Icon name="UserPlus" size={14} /> {inviting ? 'Inviting...' : 'Invite'}
          </button>
        </div>

        {tempPassword && (
          <div className={s.tempPasswordBox}>
            <div className={s.tempPasswordLabel}>Temporary password — share it with the user (shown once):</div>
            <div className={s.tempPasswordValue}>
              <span>{tempPassword}</span>
              <button className={s.btnSecondaryXSmall} onClick={copyTempPassword}>
                <Icon name="Copy" size={12} /> Copy
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Existing users */}
      <div>
        <div className={s.keyStatusTitle}>Users ({users.length})</div>
        <div className={s.userList}>
          {users.map(u => (
            <div key={u.id} className={s.userRow}>
              <div className={s.userRowInfo}>
                <div className={s.userName}>
                  {u.name || '(no name)'}
                  {u.id === currentUserId && <span className={s.youBadge}>You</span>}
                </div>
                <div className={s.userEmail}>{u.email}</div>
              </div>
              <select
                aria-label={`Role for ${u.email}`}
                className={s.userRoleSelect}
                value={u.roles[0] || 'attorney'}
                onChange={e => handleRoleChange(u, e.target.value)}
              >
                {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
          ))}
          {users.length === 0 && <span className={s.helpText}>No users found.</span>}
        </div>
      </div>

      {/* Role permissions matrix */}
      {matrix && (
        <div className={s.permSection}>
          <div className={s.permHeader}>
            <div>
              <div className={s.keyStatusTitle}>Role Permissions</div>
              <span className={s.helpText}>
                What each role can do. Defaults are prechecked — check and uncheck to
                customize; changes apply to everyone with that role immediately.
              </span>
            </div>
            {matrix.customized.length > 0 && (
              <button className={s.btnSecondaryXSmall} onClick={handleResetRoles}>
                <Icon name="RotateCcw" size={12} /> Reset to defaults
              </button>
            )}
          </div>

          <div className={s.permTableWrap}>
            <table className={s.permTable}>
              <thead>
                <tr>
                  <th className={s.permNameCol}>Permission</th>
                  {matrix.roles.map(role => (
                    <th key={role} className={s.permRoleCol}>
                      {role.charAt(0).toUpperCase() + role.slice(1)}
                      {matrix.customized.includes(role) && (
                        <span className={s.permCustomBadge} title="Differs from defaults">edited</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {permissionGroups.map(group => (
                  [
                    <tr key={group} className={s.permGroupRow}>
                      <td colSpan={matrix.roles.length + 1}>{group}</td>
                    </tr>,
                    ...matrix.permissions.filter(p => p.group === group).map(p => (
                      <tr key={p.key}>
                        <td className={s.permNameCol}>
                          <span className={s.permLabel}>{p.label}</span>
                          <span className={s.permDesc}>{p.description}</span>
                        </td>
                        {matrix.roles.map(role => (
                          <td key={role} className={s.permCheckCell}>
                            <input
                              aria-label={`${p.label} for ${role}`}
                              type="checkbox"
                              className={s.permCheckbox}
                              checked={(matrix.assigned[role] || []).includes(p.key)}
                              disabled={isLocked(role, p.key)}
                              title={isLocked(role, p.key)
                                ? 'Locked — admins always keep user management, so no one can lock everyone out'
                                : undefined}
                              onChange={() => handleTogglePermission(role, p.key)}
                            />
                          </td>
                        ))}
                      </tr>
                    )),
                  ]
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
