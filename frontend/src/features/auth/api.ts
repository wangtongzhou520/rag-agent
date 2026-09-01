import { request } from "@/shared/api/client";
import { normalizeRole, type CurrentUser, type LoginResponse } from "@/features/auth/types";

export function login(username: string, password: string) {
  return request<LoginResponse>({
    method: "POST",
    url: "/auth/login",
    data: { username, password },
  });
}

export function logout() {
  return request<null>({ method: "POST", url: "/auth/logout" });
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const user = await request<Omit<CurrentUser, "role"> & { role: string }>({
    method: "GET",
    url: "/user/me",
  });
  return { ...user, role: normalizeRole(user.role) };
}
