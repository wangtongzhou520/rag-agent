import { Bot } from "lucide-react";

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
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-600 text-white shadow-[0_10px_24px_rgb(37_99_235_/_28%)]">
        <Bot aria-hidden="true" className="h-5 w-5" />
      </span>
      {!compact && (
        <span className="leading-tight">
          <strong className="block text-[15px] font-semibold tracking-tight text-ink">
            Ragent AI
          </strong>
          <span className="text-xs text-muted">Knowledge signal workspace</span>
        </span>
      )}
    </div>
  );
}
