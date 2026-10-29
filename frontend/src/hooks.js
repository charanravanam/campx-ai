import { useCallback, useEffect, useRef, useState } from "react";

// Runs an async loader(signal) and tracks { data, error, loading }.
export function useLoad(loader, deps = []) {
  const [s, setS] = useState({ data: null, error: null, loading: true });
  const tick = useRef(0);
  const run = useCallback(() => {
    const ctl = new AbortController();
    const id = ++tick.current;
    setS((p) => ({ ...p, loading: true, error: null }));
    loader(ctl.signal)
      .then((data) => id === tick.current && setS({ data, error: null, loading: false }))
      .catch((error) => { if (error.name !== "AbortError" && id === tick.current) setS({ data: null, error, loading: false }); });
    return () => ctl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => run(), [run]);
  return { ...s, reload: run };
}

export function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}
