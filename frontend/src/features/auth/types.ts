export type UserRole = "admin" | "user";

export interface LoginResponse {
  userId: number;
  role: string;
  token: string;
  avatar?: string | null;
}

export interface CurrentUser {
  userId: number;
  username: string;
  role: UserRole;
  avatar?: string | null;
}

export function normalizeRole(role: string): UserRole {
  return role.toLowerCase() === "admin" ? "admin" : "user";
}
