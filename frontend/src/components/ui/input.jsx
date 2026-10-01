import * as React from "react"
import { cn } from "@/lib/utils"

/** Text input: 44px tall, cobalt focus border + soft halo, red border when aria-invalid. */
function Input({
  className,
  type,
  ...props
}) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-11 w-full min-w-0 rounded-md border border-input bg-surface px-3 py-2 text-base leading-snug text-foreground shadow-xs outline-none transition-[border-color,box-shadow,background-color] duration-150 selection:bg-primary selection:text-primary-foreground file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground hover:border-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-sunken disabled:text-muted-foreground disabled:opacity-80",
        "focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-ring/35",
        "aria-invalid:border-destructive aria-invalid:bg-danger/50 aria-invalid:focus-visible:ring-destructive/30",
        className
      )}
      {...props}
    />
  )
}

export { Input }
