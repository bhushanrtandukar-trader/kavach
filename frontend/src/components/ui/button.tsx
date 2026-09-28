"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const buttonVariants = cva(
  "relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium outline-none transition-all duration-200 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "gradient-bg text-primary-foreground shadow-[0_8px_24px_-10px_var(--primary)] hover:brightness-110 hover:shadow-[0_12px_32px_-10px_var(--primary)]",
        secondary: "border bg-muted text-foreground hover:bg-[color-mix(in_oklab,var(--muted)_60%,var(--foreground)_9%)]",
        outline: "border bg-transparent text-foreground hover:bg-muted",
        ghost: "text-foreground/80 hover:bg-muted hover:text-foreground",
        destructive: "bg-danger text-white shadow-[0_8px_24px_-12px_var(--danger)] hover:brightness-110",
        soft: "bg-primary/10 text-primary hover:bg-primary/15",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-8 rounded-lg px-3 text-[13px]",
        lg: "h-12 rounded-2xl px-6 text-[15px]",
        icon: "size-10",
        "icon-sm": "size-8 rounded-lg",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="absolute animate-spin" />}
      <span className={cn("inline-flex items-center gap-2", loading && "invisible")}>{children}</span>
    </button>
  ),
);
Button.displayName = "Button";
