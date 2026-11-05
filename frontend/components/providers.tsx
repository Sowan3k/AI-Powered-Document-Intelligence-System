"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

/** Motion follows the phone's "reduce motion" setting everywhere (D73). */
export function Providers({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}

/** The soft field of light the glass surfaces blur. Purely decorative. */
export function Ambient() {
  return (
    <div className="ambient" aria-hidden>
      <span />
      <span />
      <span />
    </div>
  );
}
