import * as React from "react"
import { cn } from "@/lib/utils"

/** Text input: 44px tall, hairline 8px, ink focus ring offset from the field, red border when aria-invalid. */
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
        "h-11 w-full min-w-0 rounded-[8px] border border-input bg-surface px-3 py-2 text-base leading-snug text-foreground outline-none transition-[border-color,box-shadow,background-color] duration-150 selection:bg-primary selection:text-primary-foreground file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground hover:border-foreground/40 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-sunken disabled:text-muted-foreground disabled:opacity-80",
        "focus-visible:border-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "[&::-webkit-search-cancel-button]:cursor-pointer [&::-webkit-search-cancel-button]:opacity-70 [&::-webkit-search-cancel-button]:grayscale",
        "aria-invalid:border-destructive aria-invalid:bg-danger/50 aria-invalid:focus-visible:ring-destructive",
        className
      )}
      {...props}
    />
  )
}

export { Input }
