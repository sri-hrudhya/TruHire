import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { metaApi } from '../lib/api';
import { FALLBACK_META, normalizeMeta } from '../lib/meta';
import { useAuth } from './AuthContext';

const MetaContext = createContext(normalizeMeta(FALLBACK_META));

export function MetaProvider({ children }) {
  const { token } = useAuth();
  const [meta, setMeta] = useState(() => normalizeMeta(FALLBACK_META));

  useEffect(() => {
    if (!token) return undefined;
    let cancelled = false;
    metaApi.get()
      .then((res) => { if (!cancelled) setMeta(normalizeMeta(res.data)); })
      .catch(() => { /* keep the fallback; the UI still works with the documented defaults */ });
    return () => { cancelled = true; };
  }, [token]);

  const value = useMemo(() => meta, [meta]);
  return <MetaContext.Provider value={value}>{children}</MetaContext.Provider>;
}

export const useMeta = () => useContext(MetaContext);
