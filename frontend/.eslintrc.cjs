module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react/recommended',
    'plugin:react/jsx-runtime',
    'plugin:react-hooks/recommended',
    'prettier',
  ],
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  settings: { react: { version: '18.2' } },
  rules: {
    'no-console': ['warn', { allow: ['warn', 'error'] }],
    'react/prop-types': 'off',
    // `catch {}` for deliberate best-effort operations is fine.
    'no-empty': ['error', { allowEmptyCatch: true }],
    // Apostrophes/quotes in JSX copy are fine; escaping them hurts readability.
    'react/no-unescaped-entities': 'off',
    // Underscore prefix marks intentionally-unused (e.g. dev-gated logger args).
    '@typescript-eslint/no-unused-vars': [
      'error',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
    ],
  },
  overrides: [
    {
      files: ['**/*.test.{js,jsx,ts,tsx}', 'src/test/**', 'e2e/**'],
      env: { jest: true },
      rules: {
        // Tests routinely stub/cast with `any`; strictness stays on for src.
        '@typescript-eslint/no-explicit-any': 'off',
      },
      globals: {
        describe: 'readonly',
        it: 'readonly',
        expect: 'readonly',
        vi: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
      },
    },
  ],
};
