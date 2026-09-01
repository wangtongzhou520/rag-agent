import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/shared/lib/cn";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-11 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-ink outline-none transition placeholder:text-[var(--text-muted)] hover:border-[var(--border-strong)] focus:border-brand-500 focus:shadow-focus disabled:bg-slate-50 disabled:text-slate-400",
        className,
      )}
      {...props}
    />
  ),
);

Input.displayName = "Input";
