import { describe, it, expect } from 'vitest';
import { cleanMarkdown } from './markdownUtils';

describe('markdownUtils', () => {
  describe('cleanMarkdown', () => {
    it('removes heading markers', () => {
      expect(cleanMarkdown('# Heading 1')).toBe('Heading 1');
      expect(cleanMarkdown('## Heading 2')).toBe('Heading 2');
      expect(cleanMarkdown('### Heading 3')).toBe('Heading 3');
      expect(cleanMarkdown('###### Heading 6')).toBe('Heading 6');
    });

    it('removes bold markers', () => {
      expect(cleanMarkdown('This is **bold** text')).toBe('This is bold text');
    });

    it('removes italic markers', () => {
      expect(cleanMarkdown('This is *italic* text')).toBe('This is italic text');
    });

    it('removes underline bold markers', () => {
      expect(cleanMarkdown('This is __underline bold__ text')).toBe('This is underline bold text');
    });

    it('removes underline italic markers', () => {
      expect(cleanMarkdown('This is _underline italic_ text')).toBe('This is underline italic text');
    });

    it('removes inline code backticks', () => {
      expect(cleanMarkdown('Use `const` keyword')).toBe('Use const keyword');
    });

    it('handles combined markdown formatting', () => {
      expect(cleanMarkdown('## **Bold Heading** with `code`')).toBe('Bold Heading with code');
    });

    it('trims whitespace', () => {
      expect(cleanMarkdown('  spaced text  ')).toBe('spaced text');
    });

    it('handles plain text with no markdown', () => {
      expect(cleanMarkdown('No formatting here')).toBe('No formatting here');
    });

    it('handles empty string', () => {
      expect(cleanMarkdown('')).toBe('');
    });

    it('handles text with only markdown symbols', () => {
      expect(cleanMarkdown('****')).toBe('');
    });

    it('removes multiple bold markers in same string', () => {
      expect(cleanMarkdown('**first** and **second**')).toBe('first and second');
    });
  });
});
