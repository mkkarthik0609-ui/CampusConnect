import { useEffect, useRef, useSyncExternalStore } from "react";
import { WifiOff } from "lucide-react";
import { toast } from "sonner";

const subscribe = (cb) => {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
};

/** Live `navigator.onLine`. */
export function useOnline() {
  return useSyncExternalStore(subscribe, () => navigator.onLine, () => true);
}

/**
 * Slim banner under the top of the shell while the browser is offline; a toast confirms when the connection returns.
 * Browsers only know about the network adapter, not the server, so this is a hint, never a gate.
 */
export function OfflineBanner() {
  const online = useOnline();
  const was = useRef(online);

  useEffect(() => {
    if (online && !was.current) toast.success("You are back online.");
    was.current = online;
  }, [online]);

  if (online) return null;
  return (
    <div
      role="status"
      className="offline-banner sticky top-[60px] z-20 flex items-center justify-center gap-2.5 border-b border-warn-line bg-warn px-4 py-2 text-center text-[0.8125rem] font-medium text-warn-ink lg:top-0"
    >
      <WifiOff aria-hidden="true" className="size-4 shrink-0" />
      <span>You are offline. Changes will not be saved until your connection returns.</span>
    </div>
  );
}
