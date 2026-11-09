import { cn } from "@/lib/utils"

function Skeleton({
  className,
  ...props
}) {
  return (
    <div
      data-slot="skeleton"
      className={cn("cc-shimmer rounded-[8px] bg-sunken", className)}
      {...props}
    />
  )
}

export { Skeleton }
