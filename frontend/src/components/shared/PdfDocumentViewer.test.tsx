import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PdfDocumentViewer } from './PdfDocumentViewer';

vi.mock('./Icon', () => ({
  Icon: ({ name, ...rest }: any) => <span data-testid={`icon-${name}`} {...rest} />,
}));

describe('PdfDocumentViewer', () => {
  it('renders without crashing', () => {
    const { container } = render(<PdfDocumentViewer fileUrl="https://example.com/test.pdf" />);
    expect(container).toBeTruthy();
  });

  it('renders Document Preview label', () => {
    render(<PdfDocumentViewer fileUrl="https://example.com/test.pdf" />);
    expect(screen.getByText('Document Preview')).toBeTruthy();
  });

  it('renders iframe with correct src', () => {
    const { container } = render(<PdfDocumentViewer fileUrl="https://example.com/test.pdf" />);
    const iframe = container.querySelector('iframe');
    expect(iframe).toBeTruthy();
    expect(iframe?.getAttribute('src')).toBe('https://example.com/test.pdf#navpanes=0&view=FitH');
  });

  it('renders iframe with title', () => {
    const { container } = render(<PdfDocumentViewer fileUrl="https://example.com/test.pdf" />);
    const iframe = container.querySelector('iframe');
    expect(iframe?.getAttribute('title')).toBe('Document viewer');
  });

  it('displays word count when provided', () => {
    render(<PdfDocumentViewer fileUrl="https://example.com/test.pdf" wordCount={1500} />);
    expect(screen.getByText('1,500 words (extracted)')).toBeTruthy();
  });

  it('does not display word count when not provided', () => {
    const { container } = render(<PdfDocumentViewer fileUrl="https://example.com/test.pdf" />);
    expect(container.textContent).not.toContain('words (extracted)');
  });
});
