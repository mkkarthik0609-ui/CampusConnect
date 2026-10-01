import * as React from "react"
import { cn } from "@/lib/utils"

function Textarea({
  className,
  ...props
}) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex min-h-[5.5rem] w-full rounded-md border border-input bg-surface px-3 py-2 text-base leading-snug text-foreground shadow-xs outline-none transition-[border-color,box-shadow,background-color] duration-150 placeholder:text-muted-foreground hover:border-muted-foreground disabled:cursor-not-allowed disabled:bg-sunken disabled:text-muted-foreground disabled:opacity-80",
        "focus-visible:border-primary focus-visible:ring-[3px] focus-visible:ring-ring/35",
        "aria-invalid:border-destructive aria-invalid:bg-danger/50 aria-invalid:focus-visible:ring-destructive/30",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
