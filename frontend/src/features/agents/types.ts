export type PromptGroup = "WORKFLOW" | "AGENT" | "COMMON";

export interface AgentProfile {
  id: number;
  name: string;
  description?: string | null;
  avatar?: string | null;
  builtin: boolean;
  active: boolean;
  effectiveSlots: number;
  inactiveSlots: number;
  createTime: number;
  updateTime: number;
}

export interface AgentProfileList {
  mode: string;
  effectiveSlotTotal: number;
  agents: AgentProfile[];
}

export interface PromptSlot {
  slotKey: string;
  displayName: string;
  group: PromptGroup;
  groupName: string;
  effective: boolean;
  inactiveReason?: string | null;
  requiredPlaceholders: string[];
  content: string;
}

export interface AgentPromptConfig {
  agentId: number;
  agentName: string;
  builtin: boolean;
  defaultAgentName: string;
  mode: string;
  slots: PromptSlot[];
}

export interface AgentProfileWrite {
  name: string;
  description?: string;
  avatar?: string;
}
