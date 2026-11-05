"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { applyTheme, chooseTheme, currentTheme, storedTheme, systemTheme, type Theme } from "@/lib/theme";

/**
 * Keeps the browser's bars in the page's colours, and follows the phone's
 * own setting while no choice has been made. Mounted once, in Providers.
 */
export function ThemeSync() {
  useEffect(() => {
    applyTheme(storedTheme() ?? systemTheme());
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const follow = () => {
      if (!storedTheme()) applyTheme(systemTheme());
    };
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, []);
  return null;
}

/**
 * A sun and moon button that switches light and dark (D81). The new theme
 * spreads from the button in a circle, through the View Transitions API;
 * without it, or with reduced motion, the switch is instant.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const button = useRef<HTMLButtonElement>(null);
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    // The theme is set before React runs (THEME_SCRIPT), so read it after mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(currentTheme());
    const onTheme = (e: Event) => setTheme((e as CustomEvent<Theme>).detail);
    window.addEventListener("docintel:theme", onTheme);
    return () => window.removeEventListener("docintel:theme", onTheme);
  }, []);

  function toggle() {
    const next: Theme = currentTheme() === "dark" ? "light" : "dark";
    const swap = () =>
      flushSync(() => {
        chooseTheme(next);
        setTheme(next);
      });
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (calm || !document.startViewTransition || !button.current) {
      swap();
      return;
    }
    const box = button.current.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const reach = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    const root = document.documentElement;
    root.dataset.theming = "";
    const transition = document.startViewTransition(swap);
    transition.ready
      .then(() =>
        root.animate(
          { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${reach}px at ${x}px ${y}px)`] },
          { duration: 560, easing: "cubic-bezier(0.3, 0.7, 0.2, 1)", pseudoElement: "::view-transition-new(root)" },
        ),
      )
      .catch(() => {});
    transition.finished.finally(() => delete root.dataset.theming);
  }

  const dark = theme === "dark";
  return (
    <button
      ref={button}
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
      className={`relative grid size-9 shrink-0 place-items-center rounded-full text-muted transition-colors hover:text-foreground ${className}`}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        {theme && (
          <motion.span
            key={theme}
            initial={{ rotate: -90, scale: 0.4, opacity: 0 }}
            animate={{ rotate: 0, scale: 1, opacity: 1 }}
            exit={{ rotate: 90, scale: 0.4, opacity: 0 }}
            transition={{ type: "spring", stiffness: 420, damping: 26 }}
            className="grid place-items-center"
          >
            {dark ? <MoonIcon /> : <SunIcon />}
          </motion.span>
        )}
      </AnimatePresence>
    </button>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5 fill-none stroke-current stroke-2 [stroke-linecap:round]" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5 fill-none stroke-current stroke-2 [stroke-linecap:round] [stroke-linejoin:round]" aria-hidden>
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
    </svg>
  );
}
