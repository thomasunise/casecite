import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./client', () => {
  const api = {
    request: vi.fn(),
    authFetch: vi.fn(),
  };
  return { api, API_BASE_URL: 'http://localhost:8000/api/v1' };
});

import { api } from './client';
import './pickers';

describe('api/pickers', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('registers expected methods on api object', () => {
    expect(typeof (api as any).getPickerConfig).toBe('function');
    expect(typeof (api as any).importFromGooglePicker).toBe('function');
    expect(typeof (api as any).importFromOneDrivePicker).toBe('function');
    expect(typeof (api as any).importFromBoxPicker).toBe('function');
    expect(typeof (api as any).importFromDropboxChooser).toBe('function');
  });

  it('getPickerConfig calls GET /pickers/config', async () => {
    (api.request as any).mockResolvedValue({ google: true, microsoft: true });
    const result = await (api as any).getPickerConfig();
    expect(api.request).toHaveBeenCalledWith('/pickers/config');
    expect(result.google).toBe(true);
  });

  it('importFromGooglePicker sends POST to /pickers/google/import', async () => {
    const files = [{ id: 'g1', name: 'doc.pdf' }];
    (api.request as any).mockResolvedValue({ message: 'imported' });
    await (api as any).importFromGooglePicker(files);
    expect(api.request).toHaveBeenCalledWith('/pickers/google/import', {
      method: 'POST',
      body: JSON.stringify(files),
    });
  });

  it('importFromOneDrivePicker sends POST to /pickers/microsoft/import', async () => {
    const files = [{ id: 'od1', name: 'doc.docx' }];
    (api.request as any).mockResolvedValue({ message: 'imported' });
    await (api as any).importFromOneDrivePicker(files);
    expect(api.request).toHaveBeenCalledWith('/pickers/microsoft/import', {
      method: 'POST',
      body: JSON.stringify(files),
    });
  });

  it('importFromBoxPicker sends POST to /pickers/box/import', async () => {
    const files = [{ id: 'b1', name: 'contract.pdf' }];
    (api.request as any).mockResolvedValue({ message: 'imported' });
    await (api as any).importFromBoxPicker(files);
    expect(api.request).toHaveBeenCalledWith('/pickers/box/import', {
      method: 'POST',
      body: JSON.stringify(files),
    });
  });

  it('importFromDropboxChooser sends POST to /pickers/dropbox/import', async () => {
    const files = [{ id: 'db1', name: 'brief.pdf' }];
    (api.request as any).mockResolvedValue({ message: 'imported' });
    await (api as any).importFromDropboxChooser(files);
    expect(api.request).toHaveBeenCalledWith('/pickers/dropbox/import', {
      method: 'POST',
      body: JSON.stringify(files),
    });
  });
});
