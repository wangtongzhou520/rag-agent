import { cn } from "@/shared/lib/cn";

const stages = ["问题", "改写", "意图", "检索", "重排", "回答"];

export function RagSignalRail({
  active = 2,
  compact = false,
}: {
  active?: number;
  compact?: boolean;
}) {
  return (
    <div className={cn("signal-rail", compact && "signal-rail--compact")} aria-label="RAG 处理链路">
      {stages.map((stage, index) => (
        <div className="signal-stage" key={stage}>
          <span
            className={cn(
              "signal-stage__dot",
              index < active && "signal-stage__dot--done",
              index === active && "signal-stage__dot--active",
            )}
          />
          <span className="signal-stage__label">{stage}</span>
          {index < stages.length - 1 && <span className="signal-stage__line" aria-hidden="true" />}
        </div>
      ))}
    </div>
  );
}
