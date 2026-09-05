import type {
  AgentProfileList,
  AgentProfileWrite,
  AgentPromptConfig,
} from "@/features/agents/types";
import { request } from "@/shared/api/client";

export function listAgents() {
  return request<AgentProfileList>({ method: "GET", url: "/agents" });
}

export function createAgent(value: AgentProfileWrite) {
  return request<string>({ method: "POST", url: "/agents", data: value });
}

export function updateAgent(id: number, value: AgentProfileWrite) {
  return request<null>({ method: "PUT", url: `/agents/${id}`, data: value });
}

export function deleteAgent(id: number) {
  return request<null>({ method: "DELETE", url: `/agents/${id}` });
}

export function activateAgent(id: number) {
  return request<null>({ method: "POST", url: `/agents/${id}/activate` });
}

export function getAgentPrompts(id: number) {
  return request<AgentPromptConfig>({ method: "GET", url: `/agents/${id}/prompts` });
}

export function saveAgentPrompt(id: number, slotKey: string, content: string) {
  return request<null>({
    method: "PUT",
    url: `/agents/${id}/prompts/${slotKey}`,
    data: { content },
  });
}

export function getDefaultPrompt(slotKey: string) {
  return request<string>({ method: "GET", url: `/agents/prompt-slots/${slotKey}/default` });
}
