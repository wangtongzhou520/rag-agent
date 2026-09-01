import { create } from "zustand";

import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
} from "@/features/auth/api";
import type { CurrentUser } from "@/features/auth/types";
import { registerUnauthorizedHandler, tokenStorage } from "@/shared/api/client";

interface AuthState {
  token: string | null;
  user: CurrentUser | null;
  ready: boolean;
  busy: boolean;
  initialize: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: tokenStorage.get(),
  user: null,
  ready: false,
  busy: false,
  initialize: async () => {
    const token = tokenStorage.get();
    if (!token) {
      set({ token: null, user: null, ready: true });
      return;
    }
    try {
      const user = await getCurrentUser();
      set({ token, user, ready: true });
    } catch {
      tokenStorage.clear();
      set({ token: null, user: null, ready: true });
    }
  },
  login: async (username, password) => {
    set({ busy: true });
    try {
      const result = await loginRequest(username, password);
      tokenStorage.set(result.token);
      const user = await getCurrentUser();
      set({ token: result.token, user, ready: true });
    } catch (error) {
      tokenStorage.clear();
      set({ token: null, user: null });
      throw error;
    } finally {
      set({ busy: false });
    }
  },
  logout: async () => {
    set({ busy: true });
    try {
      await logoutRequest();
    } catch {
      // Local session cleanup must still succeed if the API is unavailable.
    } finally {
      tokenStorage.clear();
      set({ token: null, user: null, ready: true, busy: false });
    }
  },
  clear: () => {
    tokenStorage.clear();
    set({ token: null, user: null, ready: true, busy: false });
  },
}));

registerUnauthorizedHandler(() => useAuthStore.getState().clear());
