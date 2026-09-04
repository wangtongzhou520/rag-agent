export interface AuditLog {
  id: number;
  bizType: string;
  bizId: string;
  operationType: string;
  actionDesc: string;
  beforeSnapshot?: unknown;
  afterSnapshot?: unknown;
  changeDiff?: Array<{ field: string; before: unknown; after: unknown }> | null;
  operatorId: string;
  operatorName?: string | null;
  operatorRole?: string | null;
  success: boolean;
  errorMessage?: string | null;
  className: string;
  methodName: string;
  ip?: string | null;
  userAgent?: string | null;
  createTime: number;
}

export interface AuditFilters {
  bizType: string;
  bizId: string;
  operationType: string;
  operatorName: string;
  success: string;
  beginTime: string;
  endTime: string;
}
