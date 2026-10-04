import { describe, it, expect } from 'vitest';
import { validateNewPassword } from './passwordPolicy';

describe('validateNewPassword', () => {
  it('accepts a password that meets the policy', () => {
    expect(validateNewPassword('Correct-Horse-9', 'Correct-Horse-9')).toBeNull();
  });

  it('rejects short passwords', () => {
    expect(validateNewPassword('Ab1!')).toMatch(/12 characters/);
  });

  it('requires all four character classes', () => {
    expect(validateNewPassword('alllowercase1234!')).toMatch(/uppercase/);
    expect(validateNewPassword('ALLUPPERCASE1234!')).toMatch(/uppercase/);
    expect(validateNewPassword('NoDigitsHereAtAll!')).toMatch(/number/);
    expect(validateNewPassword('NoSymbolsHere1234')).toMatch(/special/);
  });

  it('rejects four identical characters in a row, like the server', () => {
    expect(validateNewPassword('Aaaaa-Horse-91!')).toMatch(/identical/);
    expect(validateNewPassword('Aaa-Horse-9111!')).toBeNull();
  });

  it('checks the confirmation only when one is given', () => {
    expect(validateNewPassword('Correct-Horse-9', 'Correct-Horse-8')).toBe('Passwords do not match');
    expect(validateNewPassword('Correct-Horse-9')).toBeNull();
  });
});
