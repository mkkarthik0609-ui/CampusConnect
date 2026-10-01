import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

/** Two overlapping discs: student + faculty, with the shared overlap cut out. */
export function BrandMark({ size = 32, className }) {
  return (
    <svg className={cn("shrink-0", className)} width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="8" fill="var(--mark-bg, #2444c7)" />
      <circle cx="12.5" cy="16" r="6.5" fill="#ffffff" />
      <circle cx="20" cy="16" r="6.5" fill="#f0a30a" fillOpacity="0.92" />
      <path d="M16.25 10.9a6.5 6.5 0 0 1 0 10.2 6.5 6.5 0 0 1 0-10.2Z" fill="var(--mark-bg, #2444c7)" />
    </svg>
  );
}

/** Mark + "CampusConnect" wordmark. Colour inherits from the parent (white inside dark chrome). */
export function Brand({ to = "/", size = 32, className, wordClassName, accentClassName = "text-saffron", asText = false, ...rest }) {
  const inner = (
    <>
      <BrandMark size={size} />
      <span className={cn("font-display text-[1.2rem] leading-none font-bold tracking-[-0.02em]", wordClassName)}>
        Campus<span className={accentClassName}>Connect</span>
      </span>
    </>
  );
  const cls = cn("inline-flex items-center gap-2.5 rounded-sm no-underline hover:text-inherit", className);
  if (asText) return <span className={cls}>{inner}</span>;
  return (
    <Link to={to} className={cls} aria-label="Campus Connect home" {...rest}>
      {inner}
    </Link>
  );
}
