import * as React from "react"
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"

/**
 * Campus Connect button. Variants map to the old .btn / .btn-outline / .btn-muted / .btn-danger.
 *  - default:     cobalt action (one per view, ideally)
 *  - outline:     secondary action
 *  - secondary:   quiet filled ("muted") action
 *  - saffron:     attention action (use very sparingly)
 *  - destructive: irreversible
 *  - ghost/link:  inline/tertiary
 * Touch targets are 44px on coarse pointers.
 */
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md border border-transparent text-[0.94rem] leading-tight font-[650] whitespace-nowrap no-underline transition-[background-color,border-color,color,transform] duration-150 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/60 focus-visible:ring-offset-0 active:translate-y-px disabled:pointer-events-none disabled:opacity-55 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-[1.1em]",
  {
    variants: {
      variant: {
        default:
          "border-primary bg-primary text-primary-foreground hover:border-primary-hover hover:bg-primary-hover active:bg-primary-press",
        outline:
          "border-line-strong bg-transparent text-primary hover:border-primary hover:bg-primary-soft hover:text-primary-ink",
        secondary:
          "bg-sunken text-foreground hover:bg-line active:bg-line-strong",
        saffron:
          "border-saffron bg-saffron text-on-saffron hover:brightness-95",
        destructive:
          "border-destructive bg-destructive text-destructive-foreground hover:brightness-90",
        ghost:
          "text-foreground hover:bg-primary-soft hover:text-primary-ink",
        link: "h-auto min-h-0 rounded-sm px-0 text-primary underline-offset-4 hover:underline hover:text-primary-hover",
      },
      size: {
        default: "min-h-[42px] px-[1.05rem] py-2 pointer-coarse:min-h-11",
        xs: "min-h-7 gap-1 rounded-sm px-2 text-xs pointer-coarse:min-h-11",
        sm: "min-h-[34px] rounded-[9px] px-3 py-1 text-sm pointer-coarse:min-h-11 pointer-coarse:px-4",
        lg: "min-h-12 rounded-lg px-6 text-base",
        icon: "size-11",
        "icon-sm": "size-9 pointer-coarse:size-11",
        "icon-xs": "size-7",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
