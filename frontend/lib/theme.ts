// Light and dark mode (D81). The page carries data-theme="light" or "dark" on
// <html>; every colour token and Tailwind's dark: variant read it. A choice
// made with the toggle is kept in localStorage; with no choice, the theme
// follows the phone's setting, live.

export type Theme = "light" | "dark";

export const THEME_KEY = "docintel.theme";
export const THEME_COLORS: Record<Theme, string> = { light: "#f3efe6", dark: "#0b121d" };

/**
 * Runs in <head> before the first paint, so the page never flashes the wrong
 * theme. Kept tiny and self-contained: it cannot import anything.
 */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";var r=document.documentElement;r.dataset.theme=t;r.style.colorScheme=t}catch(e){}})()`;

export function storedTheme(): Theme | null {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

export function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

/** Puts a theme on the page, and on the browser's own bars through theme-color. */
export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  for (const meta of document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')) {
    meta.content = THEME_COLORS[theme];
  }
  window.dispatchEvent(new CustomEvent("docintel:theme", { detail: theme }));
}

/** The toggle's choice: remembered, then applied. */
export function chooseTheme(theme: Theme) {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Private mode or blocked storage: the choice lasts for this page only.
  }
  applyTheme(theme);
}
