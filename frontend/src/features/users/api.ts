import type { ManagedUser, PasswordChange, UserWrite } from "@/features/users/types";
import { request } from "@/shared/api/client";
import { normalizePage, type PageResult } from "@/shared/api/result";

export async function listUsers(current: number, size: number, keyword: string) {
  const page = await request<PageResult<ManagedUser>>({
    method: "GET",
    url: "/users",
    params: { current, size, ...(keyword ? { keyword } : {}) },
  });
  return normalizePage(page);
}

export function createUser(value: Required<Pick<UserWrite, "username" | "password">> & UserWrite) {
  return request<string>({ method: "POST", url: "/users", data: value });
}

export function updateUser(id: number, value: UserWrite) {
  return request<null>({ method: "PUT", url: `/users/${id}`, data: value });
}

export function deleteUser(id: number) {
  return request<null>({ method: "DELETE", url: `/users/${id}` });
}

export function changePassword(value: PasswordChange) {
  return request<null>({ method: "PUT", url: "/user/password", data: value });
}
