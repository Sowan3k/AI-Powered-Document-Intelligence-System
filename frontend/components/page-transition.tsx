import { ViewTransition, type ReactNode } from "react";

/** Tab order decides the slide direction: moving right slides left, and back. */
export const TAB_ORDER = ["/documents", "/review", "/search", "/reconcile"] as const;

export function tabIndex(pathname: string): number {
  const i = TAB_ORDER.findIndex((href) => pathname === href || pathname.startsWith(`${href}/`));
  return i === -1 ? 0 : i;
}

/** The transition type a link from `from` to `to` should carry. */
export function direction(from: string, to: string): string[] {
  const a = tabIndex(from);
  const b = tabIndex(to);
  if (a === b) return to.startsWith(`${from}/`) ? ["nav-forward"] : [];
  return [b > a ? "nav-forward" : "nav-back"];
}

/**
 * Each page wraps its content in this, so a tab change slides the old page out
 * and the new one in (React ViewTransition on the browser's View Transitions
 * API). Navigations without a type, such as the back button, do not slide.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const slide = { "nav-forward": "nav-forward", "nav-back": "nav-back", default: "none" };
  return (
    <ViewTransition enter={slide} exit={slide} default="none">
      <div className="flex flex-col gap-5">{children}</div>
    </ViewTransition>
  );
}
