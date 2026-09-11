import { create } from "zustand";
import type { LatestVersionResponse } from "@/hooks/versionCheck";

export type AppTheme = "light" | "dark";

interface AppState {
  sidebarCollapsed: boolean;
  availableUpdate: LatestVersionResponse | null;
  theme: AppTheme;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setAvailableUpdate: (update: LatestVersionResponse | null) => void;
  toggleTheme: () => void;
  setTheme: (theme: AppTheme) => void;
}

function getInitialTheme(): AppTheme {
  const saved = localStorage.getItem("app-theme");
  if (saved === "dark" || saved === "light") {
    return saved;
  }
  // Check system preference
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

function applyTheme(theme: AppTheme) {
  if (typeof document !== "undefined") {
    if (theme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }
}

const initialTheme = getInitialTheme();
applyTheme(initialTheme);

export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: localStorage.getItem("sidebar-collapsed") === "true",
  availableUpdate: null,
  theme: initialTheme,
  toggleSidebar: () =>
    set((state) => {
      const next = !state.sidebarCollapsed;
      localStorage.setItem("sidebar-collapsed", String(next));
      return { sidebarCollapsed: next };
    }),
  setSidebarCollapsed: (collapsed) => {
    localStorage.setItem("sidebar-collapsed", String(collapsed));
    set({ sidebarCollapsed: collapsed });
  },
  setAvailableUpdate: (update) => set({ availableUpdate: update }),
  toggleTheme: () =>
    set((state) => {
      const next: AppTheme = state.theme === "dark" ? "light" : "dark";
      localStorage.setItem("app-theme", next);
      applyTheme(next);
      return { theme: next };
    }),
  setTheme: (theme) => {
    localStorage.setItem("app-theme", theme);
    applyTheme(theme);
    set({ theme });
  },
}));

