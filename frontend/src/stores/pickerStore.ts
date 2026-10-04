import { create } from 'zustand';
import { api } from '../api';
import logger from '../utils/logger';
import { loadScript } from '../utils/loadScript';
import { isAllowedOAuthUrl } from '../utils/oauthOrigins';
import { useUIStore } from './uiStore';
import { useDocumentsStore } from './documentsStore';
import { useConnectorsStore } from './connectorsStore';
import type { PickerFile } from '../types';
import type { ImportResponse } from '../api/types';

export interface PickerState {
  showPickerModal: boolean;
  setShowPickerModal: (val: boolean) => void;
  pickerLoading: boolean;
  setPickerLoading: (val: boolean) => void;
  activePickerProvider: string | null;
  setActivePickerProvider: (val: string | null) => void;

  handlePickerFilesSelected: (files: PickerFile[], provider: string) => Promise<void>;
  loadGooglePicker: () => Promise<void>;
  openGooglePicker: () => Promise<void>;
  openOneDrivePicker: () => Promise<void>;
  openDropboxChooser: () => Promise<void>;
  openBoxPicker: () => Promise<void>;
  openActivePicker: () => void;
}

const BOX_ELEMENTS_VERSION = '22.0.0';

// Google's two picker dependencies. Loaded on demand, the first time someone
// opens the Google picker — never on page load — so an instance that doesn't
// use Google Drive makes no request to Google at all.
const GOOGLE_IDENTITY_SRC = 'https://accounts.google.com/gsi/client';
const GOOGLE_API_SRC = 'https://apis.google.com/js/api.js';

// Microsoft's fixed tenant id for personal (consumer) Microsoft accounts.
const MSA_CONSUMER_TENANT_ID = '9188040d-6c67-4c5b-b112-36a304b66dad';
const ONEDRIVE_CONSUMER_ORIGIN = 'https://onedrive.live.com';
const SHAREPOINT_ORIGIN = /^https:\/\/[a-z0-9-]+\.sharepoint\.(com|us|de|cn)$/i;

/**
 * Origin of the signed-in user's OneDrive for Business / SharePoint site.
 * It is `https://<tenant-name>-my.sharepoint.com`, where the tenant *name*
 * cannot be derived from the tenant GUID — ask Graph where the drive lives.
 */
async function resolveBusinessOneDriveOrigin(graphAccessToken: string): Promise<string> {
  const resp = await fetch('https://graph.microsoft.com/v1.0/me/drive?$select=webUrl', {
    headers: { Authorization: `Bearer ${graphAccessToken}` },
  });
  if (!resp.ok) throw new Error(`Could not locate your OneDrive (Graph returned ${resp.status}).`);
  const { webUrl } = await resp.json() as { webUrl?: string };
  if (!webUrl) throw new Error('Could not locate your OneDrive.');
  const origin = new URL(webUrl).origin;
  if (!SHAREPOINT_ORIGIN.test(origin)) throw new Error('Unexpected OneDrive location.');
  return origin;
}

export const usePickerStore = create<PickerState>((set, get) => ({
  showPickerModal: false,
  setShowPickerModal: (val) => set({ showPickerModal: val }),
  pickerLoading: false,
  setPickerLoading: (val) => set({ pickerLoading: val }),
  activePickerProvider: null,
  setActivePickerProvider: (val) => set({ activePickerProvider: val }),

  handlePickerFilesSelected: async (files, provider) => {
    if (!files || files.length === 0) return;
    const { addToast } = useUIStore.getState();
    const { setDocuments } = useDocumentsStore.getState();

    set({ pickerLoading: true, showPickerModal: false });
    try {
      let result: ImportResponse;
      switch (provider) {
        case 'google': result = await api.importFromGooglePicker(files); break;
        case 'onedrive': result = await api.importFromOneDrivePicker(files); break;
        case 'box': result = await api.importFromBoxPicker(files); break;
        case 'dropbox': result = await api.importFromDropboxChooser(files); break;
        default: throw new Error('Unknown provider');
      }
      if (result.imported > 0) {
        addToast(`Imported ${result.imported} file(s) from ${provider}`, 'success');
        const docsResp = await api.getDocuments();
        setDocuments((docsResp.documents || []).map(d => ({ ...d })));
      }
      if (result.failed > 0) {
        addToast(`Failed to import ${result.failed} file(s)`, 'error');
      }
    } catch (error: unknown) {
      logger.error('Import error:', error);
      const message = error instanceof Error ? error.message : String(error);
      addToast('Failed to import files: ' + message, 'error');
    } finally {
      set({ pickerLoading: false });
    }
  },

  loadGooglePicker: async () => {
    if (window.google?.picker && window.google.accounts?.oauth2) return;
    await Promise.all([loadScript(GOOGLE_IDENTITY_SRC), loadScript(GOOGLE_API_SRC)]);
    if (window.google?.picker) return;
    await new Promise<void>((resolve, reject) => {
      if (!window.gapi) {
        reject(new Error('Google API failed to initialize.'));
        return;
      }
      window.gapi.load('picker', {
        callback: () => resolve(),
        onerror: () => reject(new Error('Google Picker failed to load.')),
        timeout: 15000,
        ontimeout: () => reject(new Error('Google Picker timed out while loading.')),
      });
    });
  },

  openGooglePicker: async () => {
    const { loadGooglePicker, handlePickerFilesSelected } = get();
    const { pickerConfig } = useConnectorsStore.getState();
    const { addToast } = useUIStore.getState();

    if (!pickerConfig?.google_enabled) {
      addToast('Google Picker not configured', 'error');
      return;
    }

    set({ pickerLoading: true });
    try {
      await loadGooglePicker();

      const google = window.google!;
      const tokenClient = google.accounts.oauth2.initTokenClient({
        client_id: pickerConfig.google_client_id || '',
        scope: 'https://www.googleapis.com/auth/drive.file',
        callback: (tokenResponse: Record<string, string>) => {
          if (tokenResponse.access_token) {
            const gPicker = google.picker!;
            const picker = new gPicker.PickerBuilder()
              .addView(new gPicker.DocsView()
                .setIncludeFolders(true)
                .setSelectFolderEnabled(false))
              .setOAuthToken(tokenResponse.access_token)
              .setDeveloperKey(pickerConfig.google_api_key || '')
              .setAppId(pickerConfig.google_app_id || '')
              .setCallback(async (data: { action: string; docs: Array<Record<string, string | number>> }) => {
                if (data.action === 'picked') {
                  const files = data.docs.map((doc) => ({
                    id: doc.id as string, name: doc.name as string, mimeType: doc.mimeType as string,
                    url: doc.url as string, sizeBytes: doc.sizeBytes as number,
                    oauthToken: tokenResponse.access_token,
                  }));
                  await handlePickerFilesSelected(files as PickerFile[], 'google');
                }
              })
              .enableFeature(gPicker.Feature.MULTISELECT_ENABLED)
              .build();
            picker.setVisible(true);
          }
          set({ pickerLoading: false });
        },
      });
      tokenClient.requestAccessToken();
    } catch (error: unknown) {
      logger.error('Google Picker error:', error);
      const message = error instanceof Error ? error.message : String(error);
      addToast('Failed to open Google Picker: ' + message, 'error');
      set({ pickerLoading: false });
    }
  },

  openOneDrivePicker: async () => {
    const { handlePickerFilesSelected } = get();
    const { pickerConfig } = useConnectorsStore.getState();
    const { addToast } = useUIStore.getState();

    if (!pickerConfig?.microsoft_enabled) {
      addToast('OneDrive Picker not configured', 'error');
      return;
    }

    set({ pickerLoading: true });
    let pickerWindow: Window | null = null;

    try {
      if (!window.__msalInstance) {
        const { PublicClientApplication } = await import('@azure/msal-browser');
        const tenantId = pickerConfig.microsoft_tenant_id || 'common';
        window.__msalInstance = new PublicClientApplication({
          auth: {
            clientId: pickerConfig.microsoft_client_id || '',
            authority: `https://login.microsoftonline.com/${tenantId}`,
            redirectUri: window.location.origin,
          },
          cache: { cacheLocation: 'sessionStorage' },
        });
        await window.__msalInstance.initialize();
      }
      const msal = window.__msalInstance;

      const baseScopes = ['Files.Read.All', 'Sites.Read.All'];
      let tokenResponse;
      try {
        tokenResponse = await msal.acquireTokenSilent({ scopes: baseScopes });
      } catch {
        tokenResponse = await msal.acquireTokenPopup({ scopes: baseScopes });
      }

      const pickerParams = {
        sdk: '8.0',
        entry: { oneDrive: { files: {} }, sharePoint: { byPath: {} } },
        authentication: {},
        messaging: { origin: window.location.origin, channelId: crypto.randomUUID() },
        selection: { mode: 'multiple' },
        typesAndSources: { mode: 'files', filters: ['.pdf', '.doc', '.docx', '.txt', '.rtf'] },
        commands: { pick: { select: { urls: { download: true } } } },
      };

      // Personal accounts all live in Microsoft's fixed consumer tenant; work
      // and school accounts use their organisation's SharePoint host.
      // (`account.environment` is the login authority host — the same value
      // for both kinds — so it cannot tell them apart.)
      const isConsumer = tokenResponse.account?.tenantId === MSA_CONSUMER_TENANT_ID;
      const baseUrl = isConsumer
        ? ONEDRIVE_CONSUMER_ORIGIN
        : await resolveBusinessOneDriveOrigin(tokenResponse.accessToken);

      // Microsoft's File Picker v8 contract: the options travel in the
      // `filePicker` query parameter and the token in the POST body.
      const pickerQuery = new URLSearchParams({ filePicker: JSON.stringify(pickerParams), locale: 'en-us' });
      const pickerUrl = isConsumer
        ? `${baseUrl}/picker?${pickerQuery}`
        : `${baseUrl}/_layouts/15/FilePicker.aspx?${pickerQuery}`;
      pickerWindow = window.open('', 'OneDrivePicker', 'width=1080,height=680,popup=1');
      if (!pickerWindow) {
        addToast('Popup blocked — please allow popups for this site', 'error');
        set({ pickerLoading: false });
        return;
      }

      const form = pickerWindow.document.createElement('form');
      form.method = 'POST';
      form.action = pickerUrl;

      const addField = (name: string, value: string) => {
        const input = pickerWindow!.document.createElement('input');
        input.type = 'hidden'; input.name = name; input.value = value;
        form.appendChild(input);
      };
      addField('access_token', tokenResponse.accessToken);

      pickerWindow.document.body.appendChild(form);
      form.submit();

      const onMessage = async (event: MessageEvent) => {
        if (event.source !== pickerWindow) return;
        // This channel hands out a live Graph access token, so accept the
        // picker's control message only from the exact picker origin. If the
        // popup is navigated to a hostile origin, its messages are ignored.
        if (event.origin !== baseUrl) return;
        if (event.data?.type !== 'initialize' || !event.ports?.[0]) return;

        window.removeEventListener('message', onMessage);
        const port = event.ports[0];
        port.start();

        port.addEventListener('message', async (portEvent: MessageEvent) => {
          const msg = portEvent.data;
          if (msg.type === 'authenticate') {
            const resource = msg.resource || '';
            const scopes = resource ? [`${resource.replace(/\/$/, '')}/.default`] : baseScopes;
            try {
              let authResp;
              try { authResp = await msal.acquireTokenSilent({ scopes }); }
              catch { authResp = await msal.acquireTokenPopup({ scopes }); }
              port.postMessage({ type: 'authenticate', accessToken: authResp.accessToken });
            } catch (err: unknown) {
              logger.error('MSAL authenticate error:', err);
              const errMessage = err instanceof Error ? err.message : String(err);
              port.postMessage({ type: 'authenticate', error: errMessage });
            }
          } else if (msg.type === 'pick') {
            const items = msg.items || [];
            const mappedFiles = items.map((item: Record<string, unknown>) => ({
              id: item.id as string, name: item.name as string, size: item.size as number,
              webUrl: item.webUrl as string,
              downloadUrl: (item['@content.downloadUrl'] as string) || null,
              accessToken: tokenResponse.accessToken,
              driveId: (item.parentReference as Record<string, string> | undefined)?.driveId || null,
            }));
            await handlePickerFilesSelected(mappedFiles as PickerFile[], 'onedrive');
            pickerWindow?.close();
            set({ pickerLoading: false });
          } else if (msg.type === 'close') {
            pickerWindow?.close();
            set({ pickerLoading: false });
          }
        });
        port.postMessage({ type: 'activate' });
      };
      window.addEventListener('message', onMessage);

      const pollTimer = setInterval(() => {
        if (pickerWindow?.closed) {
          clearInterval(pollTimer);
          window.removeEventListener('message', onMessage);
          set({ pickerLoading: false });
        }
      }, 500);
    } catch (error: unknown) {
      logger.error('OneDrive Picker error:', error);
      const message = error instanceof Error ? error.message : String(error);
      addToast('Failed to open OneDrive Picker: ' + message, 'error');
      pickerWindow?.close();
      set({ pickerLoading: false });
    }
  },

  openDropboxChooser: async () => {
    const { handlePickerFilesSelected } = get();
    const { pickerConfig } = useConnectorsStore.getState();
    const { addToast } = useUIStore.getState();

    if (!pickerConfig?.dropbox_enabled) {
      addToast('Dropbox Chooser not configured', 'error');
      return;
    }

    set({ pickerLoading: true });
    try {
      if (!window.Dropbox) {
        await loadScript('https://www.dropbox.com/static/api/2/dropins.js', {
          id: 'dropboxjs',
          attributes: { 'data-app-key': pickerConfig.dropbox_app_key || '' },
        });
      }
      if (!window.Dropbox) throw new Error('Dropbox Chooser failed to initialize.');

      window.Dropbox!.choose({
        success: async (files: Array<Record<string, unknown>>) => {
          const mappedFiles: PickerFile[] = files.map((file) => ({
            id: (file.link as string) || '',
            name: file.name as string,
            size: file.bytes as number,
            url: file.link as string,
          }));
          await handlePickerFilesSelected(mappedFiles, 'dropbox');
          set({ pickerLoading: false });
        },
        cancel: () => set({ pickerLoading: false }),
        linkType: 'direct',
        multiselect: true,
        extensions: ['.pdf', '.doc', '.docx', '.txt', '.rtf'],
      });
    } catch (error: unknown) {
      logger.error('Dropbox Chooser error:', error);
      const message = error instanceof Error ? error.message : String(error);
      addToast('Failed to open Dropbox Chooser: ' + message, 'error');
      set({ pickerLoading: false });
    }
  },

  openBoxPicker: async () => {
    const { handlePickerFilesSelected } = get();
    const { pickerConfig } = useConnectorsStore.getState();
    const { addToast } = useUIStore.getState();

    if (!pickerConfig?.box_enabled) {
      addToast('Box picker not configured', 'error');
      return;
    }

    set({ pickerLoading: true });
    try {
      // The Box Content Picker runs on a downscoped token minted from the
      // user's connected Box account.
      let token: string;
      try {
        const tokenResp = await api.getBoxPickerToken();
        token = tokenResp.access_token;
      } catch (tokenError: unknown) {
        const msg = tokenError instanceof Error ? tokenError.message : String(tokenError);
        if (msg.toLowerCase().includes('not connected')) {
          const authResp = await api.connectConnector('box');
          // Same guard as every other connector: only ever open a
          // backend-supplied URL that points at the provider itself.
          if (isAllowedOAuthUrl(authResp?.auth_url)) {
            window.open(authResp.auth_url, 'BoxAuth', 'width=600,height=700,popup=1');
            addToast('Sign in to Box in the popup, then click Browse again.', 'info');
          } else {
            addToast('Connect Box from the Sources section first.', 'info');
          }
          set({ pickerLoading: false });
          return;
        }
        throw tokenError;
      }

      if (!window.Box?.FilePicker) {
        const base = `https://cdn01.boxcdn.net/platform/elements/${BOX_ELEMENTS_VERSION}/en-US`;
        if (!document.getElementById('box-elements-css')) {
          const link = document.createElement('link');
          link.id = 'box-elements-css';
          link.rel = 'stylesheet';
          link.href = `${base}/picker.css`;
          document.head.appendChild(link);
        }
        await loadScript(`${base}/picker.js`);
        if (!window.Box?.FilePicker) throw new Error('Box picker failed to initialize.');
      }

      // Box UI Elements render into a container, so give the picker a
      // full-screen overlay it can live in until choose/cancel.
      const overlay = document.createElement('div');
      overlay.id = 'box-picker-overlay';
      overlay.setAttribute(
        'style',
        'position:fixed;inset:0;z-index:10000;background:rgba(15,23,42,0.55);display:flex;align-items:center;justify-content:center;'
      );
      const container = document.createElement('div');
      container.id = 'box-picker-container';
      container.setAttribute(
        'style',
        'width:min(720px,92vw);height:min(560px,86vh);background:#fff;border-radius:8px;overflow:hidden;'
      );
      overlay.appendChild(container);
      document.body.appendChild(overlay);

      const cleanup = () => {
        overlay.remove();
        set({ pickerLoading: false });
      };
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) cleanup();
      });

      const picker = new window.Box!.FilePicker();
      picker.addListener('choose', async (files: Array<Record<string, unknown>>) => {
        const mapped: PickerFile[] = files.map((f) => ({
          id: String(f.id ?? ''),
          name: String(f.name ?? ''),
          size: (f.size as number) || 0,
          accessToken: token,
        }));
        cleanup();
        await handlePickerFilesSelected(mapped, 'box');
      });
      picker.addListener('cancel', cleanup);
      picker.show('0', token, {
        container: '#box-picker-container',
        chooseButtonLabel: 'Import',
        canUpload: false,
        canSetShareAccess: false,
        canCreateNewFolder: false,
        extensions: ['pdf', 'doc', 'docx', 'txt', 'rtf'],
        maxSelectable: 25,
      });
    } catch (error: unknown) {
      logger.error('Box Picker error:', error);
      const message = error instanceof Error ? error.message : String(error);
      addToast('Failed to open Box picker: ' + message, 'error');
      document.getElementById('box-picker-overlay')?.remove();
      set({ pickerLoading: false });
    }
  },

  openActivePicker: () => {
    const { activePickerProvider, openGooglePicker, openOneDrivePicker, openDropboxChooser, openBoxPicker } = get();
    const { addToast } = useUIStore.getState();
    switch (activePickerProvider) {
      case 'google_drive': openGooglePicker(); break;
      case 'onedrive': openOneDrivePicker(); break;
      case 'dropbox': openDropboxChooser(); break;
      case 'box': openBoxPicker(); break;
      default:
        addToast('Picker not available for this provider', 'error');
    }
    set({ showPickerModal: false });
  },
}));
