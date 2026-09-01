import { BrainCircuit, ChevronDown } from "lucide-react";

import type { StreamPhase } from "@/features/chat/machine";
import { RagSignalRail } from "@/shared/components/RagSignalRail";

function activeStage(phase: StreamPhase, hasAnswer: boolean) {
  if (phase === "connecting") return 0;
  if (hasAnswer) return 5;
  if (phase === "finishing" || phase === "completed") return 5;
  return 3;
}

export function ThinkingPanel({
  thinking,
  phase,
  hasAnswer,
}: {
  thinking: string;
  phase: StreamPhase;
  hasAnswer: boolean;
}) {
  const active = activeStage(phase, hasAnswer);
  const running = ["connecting", "streaming", "finishing"].includes(phase);

  return (
    <details className="thinking-panel" open={running && Boolean(thinking)}>
      <summary>
        <span>
          <BrainCircuit aria-hidden="true" />
          {running ? "正在沿 RAG 链路处理" : "查看思考过程"}
        </span>
        <ChevronDown aria-hidden="true" />
      </summary>
      <div className="thinking-panel__body">
        <RagSignalRail active={active} compact />
        {thinking && <p>{thinking}</p>}
      </div>
    </details>
  );
}
