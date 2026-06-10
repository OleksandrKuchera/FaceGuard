import { create } from 'zustand';
import type { User } from '@/types';

const USER_KEY = 'fg_user';

function loadUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (raw) return JSON.parse(raw) as User;

    // Fallback: decode from stored JWT
    const token = localStorage.getItem('access_token');
    if (!token) return null;
    const payload = JSON.parse(atob(token.split('.')[1])) as Record<string, unknown>;
    return {
      username:   (payload.username   as string) ?? '',
      role:       (payload.role       as User['role']) ?? 'guard',
      first_name: (payload.first_name as string) ?? '',
      last_name:  (payload.last_name  as string) ?? '',
    };
  } catch {
    return null;
  }
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  setAuth: (user: User, access: string, refresh: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: loadUser(),
  isAuthenticated: !!localStorage.getItem('access_token'),

  setAuth: (user, access, refresh) => {
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refresh);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    set({ user, isAuthenticated: true });
  },

  logout: () => {
    const refresh = localStorage.getItem('refresh_token');
    if (refresh) {
      import('@/api/client').then(({ logout }) => logout(refresh).catch(() => {}));
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem(USER_KEY);
    set({ user: null, isAuthenticated: false });
  },
}));
