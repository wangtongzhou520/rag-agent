import { AlertCircle, CheckCircle2, Clock3, LoaderCircle } from "lucide-react";

import type { KnowledgeDocument } from "@/features/knowledge/types";

const states = {
  pending: { label: "待分块", Icon: Clock3 },
  running: { label: "处理中", Icon: LoaderCircle },
  success: { label: "已完成", Icon: CheckCircle2 },
  failed: { label: "处理失败", Icon: AlertCircle },
} as const;

export function DocumentStatusBadge({ status }: Pick<KnowledgeDocument, "status">) {
  const state = states[status as keyof typeof states];
  const Icon = state?.Icon || AlertCircle;
  return (
    <span className={`document-status document-status--${status}`}>
      <Icon aria-hidden="true" />
      {state?.label || status}
    </span>
  );
}
