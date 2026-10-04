import { api } from './client';
import type { PickerConfig, ImportResponse, BoxPickerToken } from './types';

Object.assign(api, {
  async getPickerConfig(): Promise<PickerConfig> {
    return api.request('/pickers/config');
  },

  async getBoxPickerToken(): Promise<BoxPickerToken> {
    return api.request('/pickers/box/token');
  },

  async importFromGooglePicker(files: unknown[]): Promise<ImportResponse> {
    return api.request('/pickers/google/import', {
      method: 'POST',
      body: JSON.stringify(files),
    });
  },

  async importFromOneDrivePicker(files: unknown[]): Promise<ImportResponse> {
    return api.request('/pickers/microsoft/import', {
      method: 'POST',
      body: JSON.stringify(files),
    });
  },

  async importFromBoxPicker(files: unknown[]): Promise<ImportResponse> {
    return api.request('/pickers/box/import', {
      method: 'POST',
      body: JSON.stringify(files),
    });
  },

  async importFromDropboxChooser(files: unknown[]): Promise<ImportResponse> {
    return api.request('/pickers/dropbox/import', {
      method: 'POST',
      body: JSON.stringify(files),
    });
  },
});
