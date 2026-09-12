export interface EvalResponse {
  retrievedDocIds: string[];
  retrievedChunkIds: string[];
  retrievedContexts: string[];
  retrievedScores: number[];
  retrievedContextDocIds: Array<string | null>;
  retrievalCollections: string[];
  answer?: string | null;
  answerLatencyMs?: number | null;
  mcpContext: string;
  hasMcpSuccess: boolean;
  needsClarification: boolean;
  hasMcpFailure: boolean;
  hasKb: boolean;
  subIntents: string[];
  intentLeafIds: Array<string | null>;
  latencyMs: number;
}

export interface EvalReportSummaryMetrics {
  total?: number;
  errors?: number;
  docHitRate?: number;
  mrr?: number;
  contextPrecision?: number;
  answerKeywordRecall?: number | null;
  answerCompleteRate?: number | null;
  latencyP95Ms?: number;
  answerLatencyP95Ms?: number | null;
  thresholdsPassed?: boolean;
}

export interface EvalReportSummary {
  reportId: string;
  label?: string | null;
  dataset: string;
  collections: string[];
  includeAnswers: boolean;
  summary: EvalReportSummaryMetrics;
  createdBy: number;
  createTime: number;
}

export interface EvalReportCase {
  id: string;
  question?: string;
  passed?: boolean;
  error?: string | null;
  doc_hit?: number;
  reciprocal_rank?: number;
  context_precision?: number;
  answer_keyword_recall?: number | null;
}

export interface EvalReportDetail extends EvalReportSummary {
  thresholds: Record<string, unknown>;
  cases: EvalReportCase[];
}
