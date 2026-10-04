/** Shown wherever a new password is chosen. Mirrors the server's policy. */
export const PASSWORD_POLICY_HINT =
  'At least 12 characters, with an uppercase letter, a lowercase letter, a number and a symbol.';

/**
 * Client-side mirror of the server password policy
 * (backend/app/services/password_policy.py). Returns the first problem, or
 * null when the password passes. The server remains the authority — this only
 * saves a round trip for the obvious cases.
 */
export function validateNewPassword(password: string, confirm?: string): string | null {
  if (password.length < 12) return 'Password must be at least 12 characters';
  if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password) || !/[^A-Za-z0-9]/.test(password)) {
    return 'Password must include uppercase, lowercase, number, and special character';
  }
  if (/(.)\1{3,}/.test(password)) {
    return 'Password must not contain more than 3 identical characters in a row';
  }
  if (confirm !== undefined && password !== confirm) return 'Passwords do not match';
  return null;
}
