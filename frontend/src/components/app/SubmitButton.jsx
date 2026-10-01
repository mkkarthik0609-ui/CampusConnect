import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Button with a pending state. Disables itself (and announces progress) while `loading`.
 *   <SubmitButton loading={mutation.isPending} loadingText="Signing in...">Sign in</SubmitButton>
 */
export function SubmitButton({ loading = false, loadingText, children, disabled, type = "submit", ...props }) {
  return (
    <Button type={type} disabled={disabled || loading} aria-busy={loading || undefined} {...props}>
      {loading ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
      {loading && loadingText ? loadingText : children}
    </Button>
  );
}
