import axios, { type AxiosRequestConfig } from "axios";

import { ApiError } from "@/shared/api/error";
import { unwrapResult } from "@/shared/api/result";

const TOKEN_KEY = "ragent.auth.token";
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api/ragent").replace(/\/$/, "");

let unauthorizedHandler: (() => void) | undefined;

export const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60_000,
});

http.interceptors.request.use((config) => {
  const token = window.localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = token;
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) unauthorizedHandler?.();
    const requestId = error?.response?.headers?.["x-request-id"];
    const message =
      error?.response?.data?.message ||
      (error?.code === "ERR_NETWORK" ? "网络错误，请检查服务是否已启动" : error?.message) ||
      "请求失败";
    return Promise.reject(new ApiError(message, "HTTP_ERROR", requestId, error?.response?.status));
  },
);

export function registerUnauthorizedHandler(handler: () => void) {
  unauthorizedHandler = handler;
}

export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await http.request(config);
  try {
    return unwrapResult<T>(response.data, response.status);
  } catch (error) {
    if (error instanceof ApiError && error.message.includes("未登录")) unauthorizedHandler?.();
    throw error;
  }
}

export const tokenStorage = {
  key: TOKEN_KEY,
  get: () => window.localStorage.getItem(TOKEN_KEY),
  set: (token: string) => window.localStorage.setItem(TOKEN_KEY, token),
  clear: () => window.localStorage.removeItem(TOKEN_KEY),
};
