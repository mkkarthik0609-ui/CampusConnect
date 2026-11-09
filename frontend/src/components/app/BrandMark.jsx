import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

/** Two interlocking hooks (campus + connection). Vector strokes: crisp at any size, inherits `currentColor`. */
export function BrandMark({ size = 32, className, strokeWidth = 7 }) {
  return (
    <svg
      className={cn("shrink-0", className)}
      width={size * 1.2}
      height={size}
      viewBox="0 0 120 100"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M62 10C38 13 12 26 12 50c0 18 14 26 32 22l22-10" />
      <path d="M54 40l20-9c18-7 34 3 34 21 0 22-26 38-56 40" />
    </svg>
  );
}

/** Mark + "CampusConnect" wordmark in the heading face. Colour inherits from the parent. */
export function Brand({ to = "/", size = 28, className, wordClassName, asText = false, ...rest }) {
  const inner = (
    <>
      <BrandMark size={size} />
      <span className={cn("font-display text-[1.2rem] leading-none font-medium tracking-[-0.03em]", wordClassName)}>
        CampusConnect
      </span>
    </>
  );
  const cls = cn("inline-flex items-center gap-2.5 rounded-sm text-ink no-underline hover:text-ink", className);
  if (asText) return <span className={cls}>{inner}</span>;
  return (
    <Link to={to} className={cls} aria-label="CampusConnect home" {...rest}>
      {inner}
    </Link>
  );
}
