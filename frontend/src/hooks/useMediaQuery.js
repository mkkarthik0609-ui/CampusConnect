import { useSyncExternalStore } from "react";

/** Subscribe to a CSS media query (correct on first render; client-only app). useMediaQuery("(min-width: 60rem)") */
export function useMediaQuery(query) {
  return useSyncExternalStore(
    (notify) => {
      const mq = window.matchMedia(query);
      mq.addEventListener("change", notify);
      return () => mq.removeEventListener("change", notify);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
