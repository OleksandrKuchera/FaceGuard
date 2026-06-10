import { create } from 'zustand';

export interface AlertItem {
  id: string;           // event_id as string, or generated uuid
  level: 'low' | 'medium' | 'high';
  message: string;
  camera_id: number;
  event_id: number | null;
  timestamp: string;    // ISO string
  acknowledged: boolean;
}

interface AlertStore {
  alerts: AlertItem[];
  panelOpen: boolean;
  addAlert: (a: Omit<AlertItem, 'acknowledged'>) => void;
  acknowledge: (id: string) => void;
  acknowledgeAll: () => void;
  clearAcknowledged: () => void;
  openPanel: () => void;
  closePanel: () => void;
  togglePanel: () => void;
  unreadCount: () => number;
}

export const useAlertStore = create<AlertStore>((set, get) => ({
  alerts: [],
  panelOpen: false,

  addAlert: (a) => set(state => {
    // Deduplicate by id
    if (state.alerts.some(x => x.id === a.id)) return state;
    return { alerts: [{ ...a, acknowledged: false }, ...state.alerts].slice(0, 100) };
  }),

  acknowledge: (id) => set(state => ({
    alerts: state.alerts.map(a => a.id === id ? { ...a, acknowledged: true } : a),
  })),

  acknowledgeAll: () => set(state => ({
    alerts: state.alerts.map(a => ({ ...a, acknowledged: true })),
  })),

  clearAcknowledged: () => set(state => ({
    alerts: state.alerts.filter(a => !a.acknowledged),
  })),

  openPanel:   () => set({ panelOpen: true }),
  closePanel:  () => set({ panelOpen: false }),
  togglePanel: () => set(state => ({ panelOpen: !state.panelOpen })),

  unreadCount: () => get().alerts.filter(a => !a.acknowledged).length,
}));
