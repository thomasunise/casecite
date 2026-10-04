/* eslint-disable no-console -- dev-gated logger; the one sanctioned console gateway */
const isDev = import.meta.env.DEV;

const noop = (..._args: unknown[]) => {};

const logger = {
  debug: isDev ? (...args: unknown[]) => console.log(...args) : noop,
  info: isDev ? (...args: unknown[]) => console.info(...args) : noop,
  warn: isDev ? (...args: unknown[]) => console.warn(...args) : noop,
  error: (...args: unknown[]) => console.error(...args),
};

export default logger;
