// Shared navigation helpers so every page handles "Back" and post-login redirects the same way.
import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export const DEFAULT_ROUTE = '/ingestion';

// sessionStorage key holding the Ingestion History filters (its URL query string), so the
// "Ingestion History" button reopens the view the user last left.
export const HISTORY_QUERY_KEY = 'truhire_ingestion_history_query';

// Only allow in-app paths as redirect targets (no protocol-relative or external URLs, no login loop).
export function safeAppPath(path) {
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') || path.startsWith('/\\')) return null;
  if (path === '/login' || path.startsWith('/login?') || path.startsWith('/login/')) return null;
  return path;
}

// Router state to attach to a <Link> so the destination can offer "Back to <label>".
export function fromState(location, label) {
  return { from: { path: `${location.pathname}${location.search}`, label } };
}

// Returns { goBack, backLabel }. When the user arrived through an in-app link that recorded
// `from`, Back pops the browser history (so the previous page keeps its query/filters and the
// Forward button still works). On a direct visit there is no in-app entry to pop, so it
// navigates to the fallback instead of leaving the app.
export function useBackNavigation(fallbackPath, fallbackLabel) {
  const location = useLocation();
  const navigate = useNavigate();
  const from = location.state?.from;
  const target = safeAppPath(from?.path);

  const goBack = useCallback(() => {
    if (target && location.key !== 'default') navigate(-1);
    else navigate(target || fallbackPath);
  }, [target, location.key, navigate, fallbackPath]);

  return { goBack, backLabel: (target && from?.label) || fallbackLabel };
}
