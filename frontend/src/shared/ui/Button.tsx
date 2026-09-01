import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/shared/lib/cn";

const buttonVariants = cva(
  "inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition focus-visible:outline-none focus-visible:shadow-focus disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-brand-600 text-white shadow-panel hover:bg-brand-700 active:bg-brand-800",
        secondary: "border border-brand-200 bg-white text-brand-700 hover:bg-brand-50",
        ghost: "text-muted hover:bg-brand-50 hover:text-brand-700",
      },
    },
    defaultVariants: { variant: "primary" },
  },
);

interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ asChild, className, variant, ...props }, ref) => {
    const Component = asChild ? Slot : "button";
    return (
      <Component ref={ref} className={cn(buttonVariants({ variant }), className)} {...props} />
    );
  },
);

Button.displayName = "Button";
