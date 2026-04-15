/** Shared light/dark preference for module insights + artwork showcase (localStorage). */
export type PanelTheme = 'light' | 'dark';

const KEY = 'v3_panel_theme';

export function loadPanelTheme(): PanelTheme {
  try {
    const v = localStorage.getItem(KEY);
    if (v === 'dark' || v === 'light') {
      return v;
    }
  } catch {
    /* private mode / blocked */
  }
  return 'light';
}

export function savePanelTheme(theme: PanelTheme): void {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* ignore */
  }
}
