import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * "Branch -> Department -> Year -> Section" as breadcrumb pills. The last segment is highlighted.
 * Accepts either the API class object ({ branch, department, year, section, label }) or a label string
 * ("CSE → AIML → 3rd Year → A"), or explicit parts.
 *
 *   <ClassPath cls={row.class} />            <ClassPath label={section.label} size="lg" />
 */
export function ClassPath({ cls, label, branch, department, year, section, size = "md", className }) {
  let parts = [branch, department, year, section].filter(Boolean);
  const source = cls?.label || label;
  if (!parts.length && cls) parts = [cls.branch, cls.department, cls.year, cls.section].filter(Boolean);
  if (!parts.length && source) parts = String(source).split(/\s*(?:→|->)\s*/).filter(Boolean);
  if (!parts.length) return null;

  return (
    <span
      role="group"
      aria-label={`Class: ${parts.join(", ")}`}
      className={cn("inline-flex flex-wrap items-center gap-x-1 gap-y-1 font-semibold text-ink-2", className)}
    >
      {parts.map((part, i) => {
        const last = i === parts.length - 1;
        return (
          <span key={`${part}-${i}`} className="inline-flex items-center gap-1">
            {i > 0 ? <ChevronRight aria-hidden="true" className="size-3.5 text-muted-foreground" /> : null}
            <span
              className={cn(
                "inline-block rounded-full leading-[1.4]",
                size === "lg" ? "px-3 py-[0.22rem] text-[0.9375rem]" : "px-2.5 py-[0.12rem] text-[0.8125rem]",
                last ? "bg-primary-soft font-bold text-primary-ink" : "bg-sunken text-ink-2",
              )}
            >
              {part}
            </span>
          </span>
        );
      })}
    </span>
  );
}
