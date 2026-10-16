import { useEffect, useState } from 'react';

// Uploaded files are only served by authenticated API routes, and <iframe>/<a href> cannot
// send the Bearer header, so fetch the file through axios and expose it as a blob: URL.
// `fileKey` identifies the file (e.g. a record id); pass null to skip loading.
export default function useAuthedFile(fetchFile, fileKey) {
  const [state, setState] = useState({ url: null, loading: false, error: null });

  useEffect(() => {
    if (!fileKey) {
      setState({ url: null, loading: false, error: null });
      return undefined;
    }
    let cancelled = false;
    let objectUrl = null;
    setState({ url: null, loading: true, error: null });
    fetchFile()
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setState({ url: objectUrl, loading: false, error: null });
      })
      .catch(() => {
        if (!cancelled) setState({ url: null, loading: false, error: 'The original file could not be loaded.' });
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [fileKey]);

  return state;
}
