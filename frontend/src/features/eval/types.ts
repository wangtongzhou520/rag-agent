export interface EvalResponse {
  retrievedDocIds: string[];
  retrievedChunkIds: string[];
  retrievedContexts: string[];
  retrievedScores: number[];
  retrievedContextDocIds: Array<string | null>;
  mcpContext: string;
  hasMcpSuccess: boolean;
  needsClarification: boolean;
  hasMcpFailure: boolean;
  hasKb: boolean;
  subIntents: string[];
  intentLeafIds: Array<string | null>;
  latencyMs: number;
}
