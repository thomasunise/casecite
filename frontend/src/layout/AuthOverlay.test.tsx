import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useAuthStore } from '../stores/authStore';
import { AuthOverlay } from './AuthOverlay';

// AuthOverlay opens the signup/login modals via the auth store.
describe('AuthOverlay', () => {
  beforeEach(() => {
    useAuthStore.setState({ showSignupModal: false, showLoginModal: false });
  });

  it('renders the overlay', () => {
    const { container } = render(<AuthOverlay />);
    expect(container.innerHTML).toContain('CaseCite');
  });

  it('renders Sign In button', () => {
    render(<AuthOverlay />);
    const signInBtns = screen.getAllByText(/Sign In/i);
    expect(signInBtns.length).toBeGreaterThan(0);
  });

  it('opens the signup modal when Register is clicked', () => {
    render(<AuthOverlay />);
    const registerBtns = screen.getAllByText(/Register/i);
    fireEvent.click(registerBtns[0]);
    expect(useAuthStore.getState().showSignupModal).toBe(true);
  });

  it('opens the login modal when Sign In is clicked', () => {
    render(<AuthOverlay />);
    const signInBtns = screen.getAllByText(/Sign In/i);
    fireEvent.click(signInBtns[0]);
    expect(useAuthStore.getState().showLoginModal).toBe(true);
  });
});
