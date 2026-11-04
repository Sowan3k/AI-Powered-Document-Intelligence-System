"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import type { Activity } from "@/lib/types";

type Ctx = { activity: Activity | null; refresh: () => void };
const ActivityContext = createContext<Ctx>({ activity: null, refresh: () => {} });

const FAST_MS = 2000; // while something is processing
const SLOW_MS = 12000; // when idle

/** One poll of /api/activity shared by the dock, the home page and the badges. */
export function ActivityProvider({ children }: { children: ReactNode }) {
  const [activity, setActivity] = useState<Activity | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const load = useRef<() => void>(() => {});

  useEffect(() => {
    let cancelled = false;
    load.current = async () => {
      clearTimeout(timer.current);
      let next = SLOW_MS;
      try {
        const data = await api<Activity>("/api/activity");
        if (cancelled) return;
        setActivity(data);
        if (data.active.length > 0) next = FAST_MS;
      } catch {
        // Keep the last state; the next poll tries again.
      }
      if (!cancelled) timer.current = setTimeout(() => load.current(), next);
    };
    load.current();
    return () => {
      cancelled = true;
      clearTimeout(timer.current);
    };
  }, []);

  const refresh = useCallback(() => load.current(), []);
  return <ActivityContext.Provider value={{ activity, refresh }}>{children}</ActivityContext.Provider>;
}

export function useActivity(): Ctx {
  return useContext(ActivityContext);
}
