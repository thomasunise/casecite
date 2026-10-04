import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useRagDocsStore } from '../stores/ragDocsStore';

// Mock the api module
vi.mock('../api', () => ({
  api: {
    getDocuments: vi.fn().mockResolvedValue({ documents: [] }),
    request: vi.fn().mockResolvedValue({}),
  },
  API_BASE_URL: 'http://localhost:8000/api/v1',
}));

import RagDocsView from './RagDocsView';

// RagDocsView reads state from the rag docs / settings / connectors stores.
describe('RagDocsView', () => {
  beforeEach(() => {
    useRagDocsStore.setState({
      ragDocs: [],
      ragDocsLoading: false,
      ragDocsSearchQuery: '',
      folders: [],
    });
  });

  it('renders without crashing', () => {
    const { container } = render(<RagDocsView />);
    expect(container).toBeTruthy();
  });

  it('shows the Knowledge Base heading', () => {
    render(<RagDocsView />);
    expect(screen.getByText('Knowledge Base')).toBeInTheDocument();
  });
});
