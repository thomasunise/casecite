/**
 * Shared navigate reference for Zustand stores.
 * Set once in App.tsx via useEffect; stores import appNavigate.
 */
let _navigate: (to: string) => void = () => {};

export const setNavigate = (fn: typeof _navigate) => { _navigate = fn; };
export const appNavigate = (to: string) => _navigate(to);

/** Go back to the previous in-app page (e.g. case view → the search results
 *  that opened it). Falls back to a route when there is no history to return
 *  to (deep link straight into the page). */
export const appNavigateBack = (fallback: string = '/research') => {
  if (window.history.length > 1) {
    window.history.back();
  } else {
    _navigate(fallback);
  }
};
