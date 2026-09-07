import type { RuntimeSettings } from "@/features/runtime/types";
import { request } from "@/shared/api/client";

export function getRuntimeSettings() {
  return request<RuntimeSettings>({ method: "GET", url: "/rag/settings" });
}
