import { useEffect, useId, useState } from 'react';
import { useConnectorsStore } from '../../../stores/connectorsStore';
import { useUIStore } from '../../../stores/uiStore';
import { api } from '../../../api';
import type { ConnectorCredentialStatus } from '../../../api/types';
import { Icon } from '../../shared/Icon';
import type { Connector } from '../../../types';
import logger from '../../../utils/logger';
import t from './SourcesTab.module.css';

// Document-source integrations. File-picker credentials can be set two ways,
// both first-class: .env variables (open-source self-install) or right here
// (desktop / private installs) — saved encrypted, instance-wide, applied
// immediately. Instance values beat .env.
interface SourceMeta {
  id: string;
  name: string;
  icon: string;
  picker: boolean; // true = individual file selector available in this build
  env: string[];
  /** Backend credentials provider key, when editable in this tab. */
  provider?: string;
}

const PICKER_SOURCES: SourceMeta[] = [
  { id: 'google_drive', name: 'Google Drive', icon: 'HardDrive', picker: true, provider: 'google', env: ['GOOGLE_API_KEY', 'GOOGLE_APP_ID', 'GOOGLE_CLIENT_ID'] },
  { id: 'onedrive', name: 'OneDrive & SharePoint', icon: 'Cloud', picker: true, provider: 'microsoft', env: ['MICROSOFT_CLIENT_ID', 'MICROSOFT_TENANT_ID'] },
  { id: 'box', name: 'Box', icon: 'Box', picker: true, provider: 'box', env: ['BOX_CLIENT_ID', 'BOX_CLIENT_SECRET'] },
  { id: 'dropbox', name: 'Dropbox', icon: 'Droplet', picker: true, provider: 'dropbox', env: ['DROPBOX_APP_KEY', 'DROPBOX_APP_SECRET'] },
];

const ENTERPRISE_SOURCES: SourceMeta[] = [
  { id: 'netdocuments', name: 'NetDocuments', icon: 'FileStack', picker: false, env: ['NETDOCUMENTS_CLIENT_ID', 'NETDOCUMENTS_CLIENT_SECRET'] },
  { id: 'imanage', name: 'iManage', icon: 'Database', picker: false, env: ['IMANAGE_CLIENT_ID', 'IMANAGE_CLIENT_SECRET', 'IMANAGE_BASE_URL'] },
  { id: 'clio', name: 'Clio', icon: 'Scale', picker: false, env: ['CLIO_CLIENT_ID', 'CLIO_CLIENT_SECRET'] },
  { id: 'filevine', name: 'Filevine', icon: 'FolderTree', picker: false, env: ['FILEVINE_API_KEY', 'FILEVINE_API_SECRET'] },
];

/** settings-field -> human label for the credential inputs. */
const FIELD_LABELS: Record<string, string> = {
  google_client_id: 'Client ID',
  google_client_secret: 'Client secret',
  google_api_key: 'API key (Picker)',
  google_app_id: 'App ID (project number)',
  microsoft_client_id: 'Client ID',
  microsoft_client_secret: 'Client secret',
  microsoft_tenant_id: 'Tenant ID',
  box_client_id: 'Client ID',
  box_client_secret: 'Client secret',
  dropbox_app_key: 'App key',
  dropbox_app_secret: 'App secret',
};

interface SourcesTabProps {
  s: Record<string, string>;
}

export function SourcesTab({ s }: SourcesTabProps) {
  const id = useId();
  const connectors = useConnectorsStore((st) => st.connectors);
  const addToast = useUIStore((st) => st.addToast);

  const [credStatus, setCredStatus] = useState<Record<string, ConnectorCredentialStatus>>({});
  const [openProvider, setOpenProvider] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Record<string, string>>>({});
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    api.getConnectorCredentials()
      .then((res) => {
        const byProvider: Record<string, ConnectorCredentialStatus> = {};
        for (const p of res.providers) byProvider[p.provider] = p;
        setCredStatus(byProvider);
      })
      .catch((e) => logger.debug('Connector credentials status unavailable:', e));
  }, []);

  const statusFor = (src: SourceMeta): { label: string; cls: string } => {
    const cred = src.provider ? credStatus[src.provider] : undefined;
    const c = connectors.find((x: Connector) => x.id === src.id);
    if (c?.connected) return { label: 'Connected', cls: t.connected };
    if (cred?.source === 'instance') return { label: 'Configured here', cls: t.configured };
    if (cred?.configured || (c && c.configured !== false)) return { label: 'Configured', cls: t.configured };
    return { label: 'Not configured', cls: t.notConfigured };
  };

  const saveProvider = async (provider: string) => {
    const values = Object.fromEntries(
      Object.entries(drafts[provider] || {}).filter(([, v]) => v.trim())
    );
    if (Object.keys(values).length === 0) {
      addToast('Enter at least one credential value.', 'error');
      return;
    }
    setSaving(provider);
    try {
      const status = await api.setConnectorCredentials(provider, values);
      setCredStatus((prev) => ({ ...prev, [provider]: status }));
      setDrafts((prev) => ({ ...prev, [provider]: {} }));
      addToast('Credentials saved and applied — no restart needed.', 'success');
    } catch (e) {
      logger.error('Saving connector credentials failed:', e);
      addToast(e instanceof Error ? e.message : 'Could not save credentials.', 'error');
    } finally {
      setSaving(null);
    }
  };

  const clearProvider = async (provider: string) => {
    setSaving(provider);
    try {
      const status = await api.clearConnectorCredentials(provider);
      setCredStatus((prev) => ({ ...prev, [provider]: status }));
      addToast('Instance credentials cleared — reverted to .env values.', 'success');
    } catch (e) {
      logger.error('Clearing connector credentials failed:', e);
      addToast(e instanceof Error ? e.message : 'Could not clear credentials.', 'error');
    } finally {
      setSaving(null);
    }
  };

  const renderCredForm = (src: SourceMeta) => {
    const provider = src.provider!;
    const cred = credStatus[provider];
    const fields = cred?.fields || [];
    return (
      <div className={t.credForm}>
        {fields.map((field) => (
          <label key={field} className={t.credField} htmlFor={`${id}-cred-${provider}-${field}`}>
            <span className={t.credLabel}>{FIELD_LABELS[field] || field}</span>
            <input
              id={`${id}-cred-${provider}-${field}`}
              type="password"
              className={t.credInput}
              placeholder={cred?.masked?.[field] || 'Not set'}
              value={drafts[provider]?.[field] || ''}
              onChange={(e) =>
                setDrafts((prev) => ({
                  ...prev,
                  [provider]: { ...prev[provider], [field]: e.target.value },
                }))
              }
              autoComplete="off"
            />
          </label>
        ))}
        <div className={t.credActions}>
          <button
            className={t.credSave}
            onClick={() => saveProvider(provider)}
            disabled={saving === provider}
          >
            {saving === provider
              ? <Icon name="Loader2" size={13} className={t.spin} />
              : <Icon name="Check" size={13} />}
            Save &amp; apply
          </button>
          {cred?.source === 'instance' && (
            <button
              className={t.credClear}
              onClick={() => clearProvider(provider)}
              disabled={saving === provider}
            >
              Use .env values
            </button>
          )}
        </div>
      </div>
    );
  };

  const renderGroup = (title: string, sub: string, items: SourceMeta[]) => (
    <div className={t.group}>
      <div className={t.groupTitle}>{title}</div>
      <div className={t.groupSub}>{sub}</div>
      <div className={t.list}>
        {items.map((src) => {
          const st = statusFor(src);
          const editable = !!src.provider;
          const open = openProvider === src.provider;
          return (
            <div key={src.id} className={t.rowWrap}>
              <div className={t.row}>
                <div className={t.icon}><Icon name={src.icon} size={18} /></div>
                <div className={t.info}>
                  <div className={t.name}>
                    {src.name}
                    {!src.picker && <span className={t.privateBadge}>Private Install</span>}
                  </div>
                  <div className={t.env}>
                    Set in environment:{' '}
                    {src.env.map((v, i) => (
                      <span key={v}><code>{v}</code>{i < src.env.length - 1 ? ', ' : ''}</span>
                    ))}
                  </div>
                </div>
                <span className={`${t.status} ${st.cls}`}>{st.label}</span>
                {editable && (
                  <button
                    className={open ? t.editBtnActive : t.editBtn}
                    onClick={() => setOpenProvider(open ? null : src.provider!)}
                  >
                    <Icon name="KeyRound" size={13} />
                    {open ? 'Close' : 'Set keys'}
                  </button>
                )}
              </div>
              {editable && open && renderCredForm(src)}
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className={s.tabPanel}>
      <p className={t.intro}>
        File-picker credentials can be set two ways: server environment variables (self-hosted
        installs) or entered here — stored encrypted, applied immediately, and taking precedence
        over the environment. Enterprise DMS sources remain environment-only.
      </p>

      {renderGroup(
        'File pickers',
        'Pick individual files into the knowledge base. Set keys here or via environment variables.',
        PICKER_SOURCES,
      )}

      {renderGroup(
        'Enterprise DMS & practice management',
        'Full background sync requires a Private Install with IT-managed OAuth credentials.',
        ENTERPRISE_SOURCES,
      )}
    </div>
  );
}
