import { useSyncExternalStore } from "react";
import { Loader2 } from "lucide-react";
import { isWaking, subscribeWaking } from "@/lib/api";

/** Non-blocking notice while the free-plan server wakes up (slow first request, or GETs being retried). */
export function WakeBanner() {
  const waking = useSyncExternalStore(subscribeWaking, isWaking, () => false);
  if (!waking) return null;
  return (
    <div
      role="status"
      className="fixed inset-x-0 top-0 z-[60] flex items-center justify-center gap-2.5 border-b border-info-line bg-info px-4 py-2 text-center text-[0.8125rem] font-medium text-info-ink"
    >
      <Loader2 aria-hidden="true" className="size-4 shrink-0 animate-spin motion-reduce:animate-none" />
      <span>Waking the server&hellip; this can take up to a minute on the free plan.</span>
    </div>
  );
}
