import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { useConnectorsStore } from '../../stores/connectorsStore';
import ProvidersModal from './ProvidersModal';

// ProvidersModal reads showProvidersModal from the connectors store.
function renderModal(open = true) {
  useConnectorsStore.setState({ showProvidersModal: open });
  return render(<ProvidersModal />);
}

describe('ProvidersModal', () => {
  beforeEach(() => {
    useConnectorsStore.setState({ showProvidersModal: false });
  });

  it('renders when showProvidersModal is true', () => {
    const { container } = renderModal();
    expect(container.textContent).toContain('Additional Integrations');
  });

  it('returns null when showProvidersModal is false', () => {
    const { container } = renderModal(false);
    expect(container.innerHTML).toBe('');
  });

  it('lists document management systems', () => {
    const { container } = renderModal();
    expect(container.textContent).toContain('NetDocuments');
    expect(container.textContent).toContain('iManage');
  });

  it('lists practice management integrations', () => {
    const { container } = renderModal();
    expect(container.textContent).toContain('Clio');
    expect(container.textContent).toContain('Filevine');
  });

  it('shows private install badges', () => {
    const { container } = renderModal();
    expect(container.textContent).toContain('Private Install');
  });

  it('shows full sync providers', () => {
    const { container } = renderModal();
    expect(container.textContent).toContain('Google Drive');
    expect(container.textContent).toContain('OneDrive & SharePoint');
    expect(container.textContent).toContain('Box');
    expect(container.textContent).toContain('Dropbox');
  });
});
