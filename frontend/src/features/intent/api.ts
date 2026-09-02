import type { IntentNode, IntentNodeWrite } from "@/features/intent/types";
import { request } from "@/shared/api/client";

export function listIntentTree() {
  return request<IntentNode[]>({ method: "GET", url: "/intent-tree/trees" });
}

export function createIntentNode(body: IntentNodeWrite) {
  return request<string>({ method: "POST", url: "/intent-tree", data: body });
}

export function updateIntentNode(id: number, body: IntentNodeWrite) {
  return request<null>({ method: "PUT", url: `/intent-tree/${id}`, data: body });
}

export function deleteIntentNode(id: number) {
  return request<null>({ method: "DELETE", url: `/intent-tree/${id}` });
}

export function batchIntentNodes(action: "enable" | "disable" | "delete", ids: number[]) {
  return request<null>({ method: "POST", url: `/intent-tree/batch/${action}`, data: { ids } });
}
