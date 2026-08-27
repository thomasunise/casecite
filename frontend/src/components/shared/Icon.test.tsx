import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Icon } from './Icon';

describe('Icon', () => {
  it('renders a lucide icon for a valid PascalCase name', () => {
    const { container } = render(<Icon name="Search" />);
    // lucide-react renders an SVG inside the wrapper span
    expect(container.querySelector('svg')).toBeTruthy();
  });

  it('converts kebab-case to PascalCase', () => {
    const { container } = render(<Icon name="file-text" />);
    // FileText is a valid lucide icon
    expect(container.querySelector('svg')).toBeTruthy();
  });

  it('renders a fallback span for an unknown icon', () => {
    const { container } = render(<Icon name="nonexistent-icon-xyz" />);
    expect(container.querySelector('svg')).toBeNull();
    const span = container.firstChild as HTMLElement;
    expect(span.tagName).toBe('SPAN');
  });

  it('applies clickable class when onClick is provided', () => {
    const onClick = vi.fn();
    const { container } = render(<Icon name="Search" onClick={onClick} />);
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('iconClickable');
  });

  it('does not apply clickable class when no onClick', () => {
    const { container } = render(<Icon name="Search" />);
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).not.toContain('iconClickable');
  });

  it('fires onClick handler when clicked', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    const { container } = render(<Icon name="Search" onClick={onClick} />);
    await user.click(container.firstChild as Element);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('applies custom className', () => {
    const { container } = render(<Icon name="Search" className="my-icon" />);
    expect((container.firstChild as HTMLElement).classList.contains('my-icon')).toBe(true);
  });
});
