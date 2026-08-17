/**
 * Light or dark, remembered between visits.
 *
 * The initial choice is made in a blocking script in `index.html`, before the
 * first paint, so a dark-mode reader never gets a white flash. This module is
 * only responsible for reading back what that script decided and for recording
 * a change.
 *
 * Every storage access is guarded. Private-browsing modes and locked-down
 * profiles throw on `localStorage` rather than returning null, and a colour
 * preference is not worth a blank page.
 */

export type Theme = "light" | "dark";

export const THEME_KEY = "cassette-theme";

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** What the document is currently showing. */
export function currentTheme(): Theme {
  return document.documentElement.dataset["theme"] === "dark" ? "dark" : "light";
}

/** The stored preference, or null when there is not one to be had. */
export function storedTheme(): Theme | null {
  try {
    const saved = storage()?.getItem(THEME_KEY);
    return saved === "dark" || saved === "light" ? saved : null;
  } catch {
    return null;
  }
}

/** Apply `theme` to the document and remember it if we can. */
export function applyTheme(theme: Theme): Theme {
  document.documentElement.dataset["theme"] = theme;
  try {
    storage()?.setItem(THEME_KEY, theme);
  } catch {
    // Applied for this visit; just not remembered for the next one.
  }
  return theme;
}

/** The other one. */
export function otherTheme(theme: Theme): Theme {
  return theme === "dark" ? "light" : "dark";
}
