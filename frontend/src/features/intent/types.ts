export type IntentLevel = 0 | 1 | 2;
export type IntentKind = 0 | 1 | 2;

export interface IntentNode {
  id: number;
  kbId?: number;
  intentCode: string;
  name: string;
  level: IntentLevel;
  parentCode?: string;
  description?: string;
  examples: string[];
  collectionName?: string;
  collectionNames: string[];
  kind: IntentKind;
  mcpToolId?: string;
  topK?: number;
  enabled: boolean;
  fullPath: string;
  children: IntentNode[];
}

export interface IntentNodeWrite {
  kbId?: number;
  intentCode: string;
  name: string;
  level: IntentLevel;
  parentCode?: string;
  description?: string;
  examples: string[];
  collectionName?: string;
  collectionNames: string[];
  kind: IntentKind;
  mcpToolId?: string;
  topK?: number;
  enabled: boolean;
}
