import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AiNotice, AI_NOTICE_TEXT } from './AiNotice';

describe('AiNotice', () => {
  it('renders as a note with the verification sentence', () => {
    render(<AiNotice />);
    const note = screen.getByRole('note');
    expect(note.textContent).toContain(AI_NOTICE_TEXT);
    expect(AI_NOTICE_TEXT).toMatch(/^AI-generated\./);
  });

  it('carries an icon', () => {
    const { container } = render(<AiNotice />);
    expect(container.querySelector('svg')).toBeTruthy();
  });

  it('is not dismissible', () => {
    render(<AiNotice />);
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('accepts an extra class for placement', () => {
    render(<AiNotice className="placed" />);
    expect(screen.getByRole('note').classList.contains('placed')).toBe(true);
  });
});
