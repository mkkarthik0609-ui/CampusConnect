import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "@/components/ui/input";

/** Password input with a show/hide toggle. Drop it inside <FormField> like any <Input>. */
export function PasswordInput({ className, ...props }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <Input {...props} type={visible ? "text" : "password"} className={`pr-12 ${className || ""}`} />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        className="absolute top-1/2 right-1 inline-flex size-10 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground hover:bg-primary-soft hover:text-primary-ink pointer-coarse:size-11"
      >
        {visible ? <EyeOff aria-hidden="true" className="size-[1.1rem]" /> : <Eye aria-hidden="true" className="size-[1.1rem]" />}
      </button>
    </div>
  );
}
