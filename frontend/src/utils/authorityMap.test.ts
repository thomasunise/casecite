import { describe, it, expect } from 'vitest';
import { authorityMapCoverageNote } from './authorityMap';

describe('authorityMapCoverageNote', () => {
  it('is null when the run covered everything or reported no coverage', () => {
    expect(authorityMapCoverageNote(undefined)).toBeNull();
    expect(authorityMapCoverageNote({
      document_chars: 1000,
      document_chars_read: 1000,
      document_truncated: false,
      propositions_identified: 3,
      propositions_researched: 3,
    })).toBeNull();
  });

  it('states each gap the server reported', () => {
    const note = authorityMapCoverageNote({
      document_chars: 500000,
      document_chars_read: 480000,
      document_truncated: true,
      document_windows_failed: 1,
      propositions_identified: 12,
      propositions_researched: 8,
      opinions_partially_read: 2,
    });
    expect(note).toContain('of');
    expect(note).toContain('characters were read');
    expect(note).toContain('1 section(s) could not be analysed');
    expect(note).toContain('8 of 12 propositions were researched');
    expect(note).toContain('2 opinion(s) were only partly read');
  });
});
