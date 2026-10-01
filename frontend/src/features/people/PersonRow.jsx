import { UserAvatar } from "@/components/app/UserAvatar";
import { cn } from "@/lib/utils";

/**
 * Avatar + name + a mono ID, with an optional sub line and a right-hand actions slot.
 * Used by dashboard lists, search results and chat rows so people look the same everywhere.
 */
export function PersonRow({ name, code, sub, src, size = "md", actions, className, children }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-2.5", className)}>
      <UserAvatar name={name} src={src} size={size} />
      <div className="min-w-0 flex-1 basis-40">
        <p className="m-0 truncate font-[650] leading-snug">
          {name}
          {code ? <span className="ml-2 font-mono text-[0.8125rem] font-medium text-muted-foreground">{code}</span> : null}
        </p>
        {sub ? <div className="mt-0.5 text-sm text-muted-foreground">{sub}</div> : null}
        {children}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2 max-[30rem]:w-full">{actions}</div> : null}
    </div>
  );
}
