export {};

/** Minimal structural types for dynamically-loaded third-party picker SDKs */

interface GooglePickerBuilder {
  addView(view: unknown): GooglePickerBuilder;
  setOAuthToken(token: string): GooglePickerBuilder;
  setDeveloperKey(key: string): GooglePickerBuilder;
  setAppId(appId: string): GooglePickerBuilder;
  setCallback(cb: (data: { action: string; docs: Array<Record<string, string | number>> }) => void): GooglePickerBuilder;
  enableFeature(feature: unknown): GooglePickerBuilder;
  build(): { setVisible(visible: boolean): void };
}

interface GoogleDocsView {
  setIncludeFolders(val: boolean): GoogleDocsView;
  setSelectFolderEnabled(val: boolean): GoogleDocsView;
}

interface GooglePickerApi {
  PickerBuilder: new () => GooglePickerBuilder;
  DocsView: new () => GoogleDocsView;
  Feature: { MULTISELECT_ENABLED: unknown };
}

interface GoogleAccountsOAuth2 {
  initTokenClient(config: { client_id: string; scope: string; callback: (response: Record<string, string>) => void }): { requestAccessToken(): void };
}

interface DropboxChooserOptions {
  success: (files: Array<Record<string, unknown>>) => void;
  cancel?: () => void;
  linkType?: string;
  multiselect?: boolean;
  extensions?: string[];
}

interface BoxFilePickerInstance {
  show(folderId: string, accessToken: string, options: Record<string, unknown>): void;
  hide(): void;
  addListener(event: string, cb: (files: Array<Record<string, unknown>>) => void): void;
}

interface BoxElementsApi {
  FilePicker: new () => BoxFilePickerInstance;
}

declare global {
  interface Window {
    __msalInstance?: import('@azure/msal-browser').PublicClientApplication;
    google?: {
      picker?: GooglePickerApi;
      accounts: { oauth2: GoogleAccountsOAuth2 };
    };
    gapi?: {
      load(
        api: string,
        callback: (() => void) | { callback: () => void; onerror?: () => void; timeout?: number; ontimeout?: () => void },
      ): void;
    };
    Dropbox?: {
      choose(options: DropboxChooserOptions): void;
    };
    Box?: BoxElementsApi;
  }
}
