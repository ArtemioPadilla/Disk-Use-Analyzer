/// <reference path="../.astro/types.d.ts" />

// Sidebar.astro attaches these on `window` (rather than exporting a module)
// so the plain inline `onclick="closeSidebar()"` handler and TopBar.astro's
// `window.openSidebar?.()` can reach them across separate Astro islands
// without wiring up a shared event bus for what is just "toggle a CSS class".
declare global {
  interface Window {
    openSidebar?: () => void;
    closeSidebar?: () => void;
  }
}

export {};