import { create } from 'zustand';

export interface CopilotEntity {
  type: string;
  name: string;
  id: string;
}

export interface CopilotPageContext {
  pageName: string;
  pageUrl: string;
  featureId?: string;
  selectedEntity?: CopilotEntity;
}

interface CopilotState {
  isOpen: boolean;
  panelWidth: number;
  isResizing: boolean;
  pageContext: CopilotPageContext | null;
  actions: {
    togglePanel: () => void;
    openPanel: () => void;
    closePanel: () => void;
    setPanelWidth: (width: number) => void;
    setResizing: (resizing: boolean) => void;
    setContext: (pageName: string, pageUrl: string, selectedEntity?: CopilotEntity, featureId?: string) => void;
    clearContext: () => void;
  };
}

const VISITED_KEY = 'copilot-sidebar-visited';
const WIDTH_KEY = 'copilot-panel-width';
export const PANEL_MIN_WIDTH = 360;

function initialWidth(): number {
  const saved = Number(localStorage.getItem(WIDTH_KEY));
  const w = saved >= PANEL_MIN_WIDTH ? saved : 420;
  // Cap against the current viewport so a width saved on a wide screen doesn't
  // overflow a narrower one after reload.
  const cap = typeof window !== 'undefined' ? Math.round(window.innerWidth * 0.95) : w;
  return Math.min(w, Math.max(PANEL_MIN_WIDTH, cap));
}

export const useCopilotStore = create<CopilotState>()((set) => ({
  isOpen: localStorage.getItem(VISITED_KEY) !== 'true',
  panelWidth: initialWidth(),
  isResizing: false,
  pageContext: null,
  actions: {
    togglePanel: () => set((state) => {
      if (state.isOpen) localStorage.setItem(VISITED_KEY, 'true');
      return { isOpen: !state.isOpen };
    }),
    openPanel: () => set({ isOpen: true }),
    closePanel: () => {
      localStorage.setItem(VISITED_KEY, 'true');
      set({ isOpen: false });
    },
    // Hot path during a drag — just update state. Persistence happens once on
    // drag-end (setResizing(false)), NOT per mousemove.
    setPanelWidth: (width) => set({ panelWidth: width }),
    setResizing: (resizing) => set((state) => {
      if (!resizing) {
        try { localStorage.setItem(WIDTH_KEY, String(Math.round(state.panelWidth))); } catch { /* ignore */ }
      }
      return { isResizing: resizing };
    }),
    setContext: (pageName, pageUrl, selectedEntity, featureId) =>
      set({ pageContext: { pageName, pageUrl, featureId, selectedEntity } }),
    clearContext: () => set({ pageContext: null }),
  },
}));
