import type { KeyboardEvent } from 'react';

/**
 * Keyboard activation for clickable rows that are not native buttons
 * (`role="button" tabIndex={0}`): Enter or Space runs `action`, like a real
 * button. Key events bubbling up from nested controls (links, buttons inside
 * the row) are ignored so they are not activated twice.
 */
export function activateOnKey(action: () => void) {
  return (e: KeyboardEvent<HTMLElement>) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      action();
    }
  };
}
