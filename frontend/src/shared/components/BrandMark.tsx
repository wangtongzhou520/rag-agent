import { PanelsTopLeft } from "lucide-react";

import { cn } from "@/shared/lib/cn";

export function BrandMark({
  compact = false,
  className,
}: {
  compact?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("inline-flex items-center gap-3", className)}>
      <span className="grid h-10 w-10 place-items-center rounded-lg bg-brand-600 text-white">
        <PanelsTopLeft aria-hidden="true" className="h-5 w-5" />
      </span>
      {!compact && (
        <span className="leading-tight">
          <strong className="block text-[15px] font-semibold tracking-tight text-ink">
            Ragent AI
          </strong>
          <span className="text-xs text-muted">知识检索与问答平台</span>
        </span>
      )}
    </div>
  );
}
