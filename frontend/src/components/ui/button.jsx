import * as React from "react"
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils"
import { Slot } from "radix-ui"

/**
 * Campus Connect button (Ellipsus-style): hairline 8px controls, solid-ink primary, outlined secondary.
 *  - default:     solid ink (one per view, ideally)
 *  - outline:     hairline secondary action
 *  - secondary:   quiet filled action
 *  - saffron:     attention action (use very sparingly)
 *  - destructive: irreversible
 *  - ghost/link:  inline/tertiary (link = underline wipe)
 * size="pill" is the rounded hero-CTA option. A trailing arrow icon nudges right on hover (index.css, shell block).
 * Touch targets are 44px on coarse pointers.
 */
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-[8px] border border-transparent text-[0.9375rem] leading-tight font-medium tracking-[-0.005em] whitespace-nowrap no-underline transition-[background-color,border-color,color,transform,box-shadow] duration-200 ease-out outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background active:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive motion-reduce:transition-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-[1.05em]",
  {
    variants: {
      variant: {
        default:
          "border-primary bg-primary text-primary-foreground hover:-translate-y-px hover:bg-primary-hover active:bg-primary-press motion-reduce:hover:translate-y-0",
        outline:
          "border-line-strong bg-transparent text-foreground hover:-translate-y-px hover:border-foreground hover:bg-primary-soft motion-reduce:hover:translate-y-0",
        secondary:
          "bg-sunken text-foreground hover:bg-line active:bg-line-strong",
        saffron:
          "border-saffron bg-saffron text-on-saffron hover:-translate-y-px hover:brightness-95 motion-reduce:hover:translate-y-0",
        destructive:
          "border-destructive bg-destructive text-destructive-foreground hover:-translate-y-px hover:brightness-90 motion-reduce:hover:translate-y-0",
        ghost:
          "text-foreground hover:bg-primary-soft",
        link: "h-auto min-h-0 rounded-none bg-[linear-gradient(currentColor,currentColor)] bg-[length:0%_1px] bg-[position:0_100%] bg-no-repeat px-0 py-0.5 text-foreground hover:bg-[length:100%_1px]",
      },
      size: {
        default: "min-h-[42px] px-4 py-2 pointer-coarse:min-h-11",
        xs: "min-h-7 gap-1 rounded-[6px] px-2 text-xs pointer-coarse:min-h-11",
        sm: "min-h-[34px] px-3 py-1 text-sm pointer-coarse:min-h-11 pointer-coarse:px-4",
        lg: "min-h-12 px-6 text-base",
        pill: "min-h-12 rounded-full px-7 text-base",
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
