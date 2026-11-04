"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, COLD_START_HINT_MS } from "@/lib/api";

type State<T> = { key: string | null; data: T | null; error: string | null; slowKey: string | null };

/**
 * Load `path` with the signed-in token. `pollMs` refetches while `keepPolling`
 * says so (for example, while a job is still running). `slow` turns true when
 * the first answer takes long, which usually means the free backend is waking.
 * Data from the previous path stays visible while the next one loads.
 */
export function useApi<T>(
  path: string | null,
  options: { pollMs?: number; keepPolling?: (data: T) => boolean } = {},
) {
  const { pollMs, keepPolling } = options;
  const [tick, setTick] = useState(0);
  const key = path === null ? null : `${path}#${tick}`;
  const [state, setState] = useState<State<T>>({ key: null, data: null, error: null, slowKey: null });
  const keepRef = useRef(keepPolling);
  useEffect(() => {
    keepRef.current = keepPolling;
  });
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (path === null || key === null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const slowTimer = setTimeout(() => {
      if (!cancelled) setState((s) => ({ ...s, slowKey: key }));
    }, COLD_START_HINT_MS);

    const load = async () => {
      try {
        const data = await api<T>(path);
        if (cancelled) return;
        clearTimeout(slowTimer);
        setState({ key, data, error: null, slowKey: null });
        if (pollMs && (!keepRef.current || keepRef.current(data))) {
          timer = setTimeout(load, pollMs);
        }
      } catch (error) {
        if (cancelled) return;
        clearTimeout(slowTimer);
        const message = error instanceof ApiError ? error.message : "Something went wrong.";
        setState((s) => ({ ...s, key, error: message, slowKey: null }));
      }
    };
    load();
    return () => {
      cancelled = true;
      clearTimeout(slowTimer);
      if (timer) clearTimeout(timer);
    };
  }, [path, key, pollMs]);

  return {
    data: state.data,
    error: state.key === key ? state.error : null,
    loading: key !== null && state.key !== key,
    slow: key !== null && state.slowKey === key,
    reload,
  };
}
