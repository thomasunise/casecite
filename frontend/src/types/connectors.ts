export interface Connector {
  id: string;
  name: string;
  icon: string;
  color: string;
  connected: boolean;
  configured?: boolean;
  docs: number;
}

export interface PickerConfig {
  provider?: string;
  token?: string;
  clientId?: string;
  appKey?: string;
  google_enabled?: boolean;
  google_client_id?: string;
  google_api_key?: string;
  google_app_id?: string;
  microsoft_enabled?: boolean;
  microsoft_client_id?: string;
  microsoft_tenant_id?: string;
  box_enabled?: boolean;
  dropbox_enabled?: boolean;
  dropbox_app_key?: string;
}

export interface PickerFile {
  id: string;
  name: string;
  mimeType?: string;
  size?: number;
  url?: string;
  /** Provider OAuth token scoped to the picked files (Google/OneDrive/Box). */
  accessToken?: string;
  oauthToken?: string;
}
