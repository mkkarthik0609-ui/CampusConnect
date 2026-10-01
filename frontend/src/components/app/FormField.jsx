import { Children, cloneElement, isValidElement, useId } from "react";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/**
 * Label + control + hint + error, wired for accessibility (for/id, aria-describedby, aria-invalid).
 *
 *   <FormField label="Email" hint="We never share it." error={errors.email} required>
 *     <Input type="email" value={email} onChange={...} />
 *   </FormField>
 *
 * The single child receives id / aria-describedby / aria-invalid / required. For controls that cannot take
 * those props (custom widgets) pass a function child: {({ id, describedBy, invalid }) => <Widget ... />}.
 * `error` is a string (shown, announced) or falsy.
 */
export function FormField({ label, hint, error, required, children, className, labelClassName, id: idProp }) {
  const auto = useId();
  const id = idProp || `f${auto.replace(/:/g, "")}`;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  let control;
  if (typeof children === "function") {
    control = children({ id, describedBy, invalid: !!error, required });
  } else {
    const only = Children.only(children);
    control = isValidElement(only)
      ? cloneElement(only, {
          id: only.props.id || id,
          "aria-describedby": [only.props["aria-describedby"], describedBy].filter(Boolean).join(" ") || undefined,
          "aria-invalid": error ? true : only.props["aria-invalid"],
          required: only.props.required ?? required,
        })
      : only;
  }

  return (
    <div className={cn("min-w-0", className)}>
      {label ? (
        <Label htmlFor={id} className={cn("mb-1.5 text-sm font-semibold text-ink-2", labelClassName)}>
          {label}
          {required ? <span aria-hidden="true" className="ml-0.5 text-danger-ink">*</span> : null}
        </Label>
      ) : null}
      {control}
      {hint ? <p id={hintId} className="mt-1.5 text-[0.8125rem] text-muted-foreground">{hint}</p> : null}
      {error ? <p id={errorId} role="alert" className="mt-1.5 text-[0.8125rem] font-semibold text-danger-ink">{error}</p> : null}
    </div>
  );
}
