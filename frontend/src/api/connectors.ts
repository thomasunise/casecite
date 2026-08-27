import { api } from './client';
import type { ConnectorAuthUrl, ConnectorDataResponse, ConnectorStatusResponse, MessageResponse, SyncStartResult, SyncStatusResult } from './types';

Object.assign(api, {
  async getConnectors(): Promise<ConnectorDataResponse> {
    return api.request('/connectors');
  },

  async connectConnector(connectorId: string): Promise<ConnectorAuthUrl> {
    return api.request(`/connectors/${connectorId}/auth`);
  },

  async disconnectConnector(connectorId: string): Promise<MessageResponse> {
    return api.request(`/connectors/${connectorId}/disconnect`, { method: 'POST' });
  },

  async syncConnector(connectorId: string, options: Record<string, unknown> = {}): Promise<SyncStartResult> {
    return api.request(`/connectors/${connectorId}/sync`, {
      method: 'POST',
      body: JSON.stringify(options),
    });
  },

  async getConnectorSyncStatus(connectorId: string, syncId: string): Promise<SyncStatusResult> {
    return api.request(`/connectors/${connectorId}/sync/${syncId}`);
  },

  async getConnectorStatus(connectorId: string): Promise<ConnectorStatusResponse> {
    return api.request(`/connectors/${connectorId}/status`);
  },
});
