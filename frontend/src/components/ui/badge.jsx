import * as React from "react"
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"

/**
 * Small pill. `saffron` is the unread-count badge used in the sidebar and bell.
 * For workflow states (PENDING, ACCEPTED, ...) use <StatusPill/> instead.
 */
const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border border-transparent px-2.5 py-0.5 text-[0.8125rem] leading-snug font-semibold whitespace-nowrap transition-colors [&>svg]:pointer-events-none [&>svg]:size-3.5",
  {
    variants: {
      variant: {
        default: "bg-primary-soft text-primary-ink [a&]:hover:bg-info-line",
        secondary: "bg-sunken text-ink-2 [a&]:hover:bg-line",
        outline: "border-line-strong text-foreground [a&]:hover:bg-primary-soft",
        destructive: "bg-danger text-danger-ink",
        saffron:
          "h-[1.4rem] min-w-[1.4rem] bg-saffron px-1.5 text-xs font-bold text-on-saffron tabular-nums",
        ghost: "[a&]:hover:bg-primary-soft",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
