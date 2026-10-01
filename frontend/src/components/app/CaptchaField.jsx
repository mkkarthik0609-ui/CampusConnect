import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/app/FormField";
import { authApi } from "@/lib/endpoints";
import { errorMessage } from "@/lib/api";

/**
 * Letters + numbers image captcha. Challenges are single use, so bump `resetKey` after ANY failed submit
 * (the server consumes the challenge even when other fields were wrong) to load a fresh one.
 * Reports { id, answer } through `onChange`; the form sends them as captcha_id / captcha_answer.
 */
export function CaptchaField({ resetKey = 0, onChange, error, label = "Security check" }) {
  const [challenge, setChallenge] = useState(null);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const onChangeRef = useRef(onChange);
  useEffect(() => { onChangeRef.current = onChange; });

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    setAnswer("");
    try {
      setChallenge(await authApi.captcha());
    } catch (err) {
      setChallenge(null);
      setLoadError(errorMessage(err, "Could not load the captcha. Try the refresh button."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load, resetKey]);

  // Challenges expire; quietly swap in a new one just before that happens.
  useEffect(() => {
    if (!challenge) return undefined;
    const t = setTimeout(load, Math.max(30, challenge.expires_in_seconds - 15) * 1000);
    return () => clearTimeout(t);
  }, [challenge, load]);

  useEffect(() => {
    onChangeRef.current?.({ id: challenge?.captcha_id || "", answer });
  }, [challenge, answer]);

  return (
    <FormField
      label={label}
      required
      hint="Type the letters and numbers you see. It is not case sensitive."
      error={error || loadError}
    >
      {({ id, describedBy, invalid }) => (
        <div className="grid gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-[84px] w-[240px] max-w-full items-center justify-center overflow-hidden rounded-md border bg-white">
              {challenge ? (
                <img src={challenge.image} width={240} height={84} alt="Captcha: distorted letters and numbers to type below" className="h-full w-full select-none" draggable={false} />
              ) : (
                <span className="text-sm text-muted-foreground">{loading ? "Loading captcha" : "Unavailable"}</span>
              )}
            </div>
            <Button type="button" variant="outline" size="icon" onClick={load} disabled={loading} aria-label="Show a different captcha">
              <RefreshCw aria-hidden="true" className={loading ? "animate-spin" : undefined} />
            </Button>
          </div>
          <Input
            id={id}
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={12}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            className="max-w-[240px] font-mono uppercase tracking-[0.2em]"
          />
        </div>
      )}
    </FormField>
  );
}
