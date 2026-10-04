import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { useConnectorsStore } from '../../stores/connectorsStore';
import FilePickerModal from './FilePickerModal';

// FilePickerModal reads picker state from the connectors store.
function setPickerState(overrides: Record<string, unknown> = {}) {
  useConnectorsStore.setState({
    showPickerModal: true,
    activePickerProvider: 'google_drive',
    pickerLoading: false,
    openActivePicker: vi.fn(),
    ...overrides,
  });
}

describe('FilePickerModal', () => {
  beforeEach(() => {
    useConnectorsStore.setState({
      showPickerModal: false,
      activePickerProvider: null,
      pickerLoading: false,
    });
  });

  it('renders when showPickerModal is true', () => {
    setPickerState();
    const { container } = render(<FilePickerModal />);
    expect(container.textContent).toContain('Import from Google Drive');
  });

  it('returns null when showPickerModal is false', () => {
    setPickerState({ showPickerModal: false });
    const { container } = render(<FilePickerModal />);
    expect(container.innerHTML).toBe('');
  });

  it('shows the browse button', () => {
    setPickerState();
    const { container } = render(<FilePickerModal />);
    expect(container.textContent).toContain('Browse Google Drive');
  });

  it('shows loading state when pickerLoading is true', () => {
    setPickerState({ pickerLoading: true });
    const { container } = render(<FilePickerModal />);
    expect(container.textContent).toContain('Opening Google Drive...');
  });

  it('shows disclaimer text', () => {
    setPickerState();
    const { container } = render(<FilePickerModal />);
    expect(container.textContent).toContain('Your files are imported directly');
  });
});
