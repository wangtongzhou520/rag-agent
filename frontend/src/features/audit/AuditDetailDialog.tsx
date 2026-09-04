import type { AuditLog } from "@/features/audit/types";
import { formatTraceTime } from "@/features/trace/format";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/Dialog";

function Snapshot({ title, value }: { title: string; value: unknown }) {
  return (
    <section className="audit-snapshot">
      <h3>{title}</h3>
      <pre>{value == null ? "无" : JSON.stringify(value, null, 2)}</pre>
    </section>
  );
}

export function AuditDetailDialog({
  current,
  onClose,
}: {
  current?: AuditLog;
  onClose: () => void;
}) {
  return (
    <Dialog open={Boolean(current)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="audit-detail-dialog">
        <DialogHeader>
          <DialogTitle>变更详情</DialogTitle>
          <DialogDescription>
            {current ? `${current.actionDesc} · ${formatTraceTime(current.createTime)}` : ""}
          </DialogDescription>
        </DialogHeader>
        {current && (
          <>
            <dl className="audit-detail-meta">
              <div>
                <dt>业务</dt>
                <dd>
                  {current.bizType} / {current.bizId}
                </dd>
              </div>
              <div>
                <dt>操作人</dt>
                <dd>
                  {current.operatorName || "SYSTEM"}（{current.operatorId}）
                </dd>
              </div>
              <div>
                <dt>来源 IP</dt>
                <dd>{current.ip || "—"}</dd>
              </div>
              <div>
                <dt>调用位置</dt>
                <dd>
                  {current.className}.{current.methodName}
                </dd>
              </div>
            </dl>
            {current.errorMessage && <p className="audit-detail-error">{current.errorMessage}</p>}
            <div className="audit-snapshot-grid">
              <Snapshot title="变更前" value={current.beforeSnapshot} />
              <Snapshot title="变更后" value={current.afterSnapshot} />
            </div>
            <Snapshot
              title={`字段差异（${current.changeDiff?.length || 0} 项）`}
              value={current.changeDiff}
            />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
