"use client";

import { animate, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

/** A whole number that counts up to its value when it appears or changes. */
export function CountUp({ value }: { value: number }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);
  useEffect(() => {
    if (reduce) return;
    const controls = animate(0, value, { duration: 0.7, ease: [0.16, 1, 0.3, 1], onUpdate: (v) => setShown(Math.round(v)) });
    return () => controls.stop();
  }, [value, reduce]);
  return <span className="tabular-nums">{reduce ? value : shown}</span>;
}
