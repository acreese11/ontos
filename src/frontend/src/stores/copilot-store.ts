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
  return saved >= PANEL_MIN_WIDTH ? saved : 420;
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
    setPanelWidth: (width) => {
      try { localStorage.setItem(WIDTH_KEY, String(Math.round(width))); } catch { /* ignore */ }
      set({ panelWidth: width });
    },
    setResizing: (resizing) => set({ isResizing: resizing }),
    setContext: (pageName, pageUrl, selectedEntity, featureId) =>
      set({ pageContext: { pageName, pageUrl, featureId, selectedEntity } }),
    clearContext: () => set({ pageContext: null }),
  },
}));
