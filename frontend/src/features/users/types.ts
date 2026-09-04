export type ManagedUserRole = "admin" | "user";

export interface ManagedUser {
  id: number;
  username: string;
  role: ManagedUserRole;
  avatar?: string | null;
  createTime: number;
  updateTime: number;
}

export interface UserWrite {
  username?: string;
  password?: string;
  role?: ManagedUserRole;
  avatar?: string;
}

export interface PasswordChange {
  currentPassword: string;
  newPassword: string;
}
