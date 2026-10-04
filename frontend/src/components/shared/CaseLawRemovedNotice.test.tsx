import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CaseLawRemovedNotice } from './CaseLawRemovedNotice';

describe('CaseLawRemovedNotice', () => {
  it('renders nothing when the server removed no references', () => {
    const { container: none } = render(<CaseLawRemovedNotice removed={[]} />);
    expect(none.firstChild).toBeNull();
    const { container: missing } = render(<CaseLawRemovedNotice />);
    expect(missing.firstChild).toBeNull();
  });

  it('names every removed reference', () => {
    render(<CaseLawRemovedNotice removed={['Smith v. Jones', 'In re Acme']} />);
    const note = screen.getByRole('note');
    expect(note.textContent).toContain('2 case references could not be verified');
    expect(screen.getByText('Smith v. Jones')).toBeTruthy();
    expect(screen.getByText('In re Acme')).toBeTruthy();
  });

  it('uses the singular for one reference', () => {
    render(<CaseLawRemovedNotice removed={['Doe v. Roe']} />);
    expect(screen.getByRole('note').textContent).toContain('1 case reference could not be verified against a real source and was removed');
  });
});
