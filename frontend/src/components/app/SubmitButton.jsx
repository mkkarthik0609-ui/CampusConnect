import { ArrowRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Button with a pending state. Disables itself (and announces progress) while `loading`.
 *   <SubmitButton loading={mutation.isPending} loadingText="Signing in...">Sign in</SubmitButton>
 */
export function SubmitButton({ loading = false, loadingText, children, disabled, type = "submit", className, ...props }) {
  return (
    <Button type={type} size="lg" disabled={disabled || loading} aria-busy={loading || undefined} className={cn("group", className)} {...props}>
      {loading ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
      {loading && loadingText ? loadingText : children}
      {loading ? null : <ArrowRight aria-hidden="true" className="transition-transform duration-200 group-hover:translate-x-1 motion-reduce:transition-none" />}
    </Button>
  );
}
