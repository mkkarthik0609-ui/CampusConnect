import { useEffect, useState } from "react";
import { parseApiDate } from "@/lib/format";

const clockFmt = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
const dateFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
const weekdayFmt = new Intl.DateTimeFormat(undefined, { weekday: "long" });

const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
const dayDiff = (d, now) => Math.round((startOfDay(now) - startOfDay(d)) / 86400000);

/** "10:32 AM" */
export function clock(value) {
  const d = parseApiDate(value);
  return d ? clockFmt.format(d) : "";
}

export const dayKey = (value) => (parseApiDate(value) || new Date()).toDateString();

/** Date-separator chip: Today / Yesterday / weekday (this week) / date. */
export function dayLabel(value, now = new Date()) {
  const d = parseApiDate(value) || now;
  const diff = dayDiff(d, now);
  if (diff <= 0) return "Today";
  if (diff === 1) return "Yesterday";
  return diff < 7 ? weekdayFmt.format(d) : dateFmt.format(d);
}

/** Chat-list timestamp: time today, "Yesterday", weekday this week, otherwise the date. */
export function listTime(value, now = new Date()) {
  const d = parseApiDate(value);
  if (!d) return "";
  const diff = dayDiff(d, now);
  if (diff <= 0) return clockFmt.format(d);
  if (diff === 1) return "Yesterday";
  return diff < 7 ? weekdayFmt.format(d) : dateFmt.format(d);
}

/** "last seen today at 10:32 AM" */
export function lastSeenLabel(value, now = new Date()) {
  const d = parseApiDate(value);
  if (!d) return "";
  const diff = dayDiff(d, now);
  const at = clockFmt.format(d);
  if (diff <= 0) return `last seen today at ${at}`;
  if (diff === 1) return `last seen yesterday at ${at}`;
  return `last seen ${dateFmt.format(d)} at ${at}`;
}

/**
 * Poll delay for react-query's refetchInterval: `focusedMs` while the tab is visible, `hiddenMs` in a background
 * tab, `false` (paused) while the browser is offline. Refetching resumes through react-query's own
 * focus / reconnect handling.
 */
export function usePollDelay(focusedMs, hiddenMs) {
  const read = () => ({ hidden: document.visibilityState === "hidden", online: navigator.onLine !== false });
  const [state, setState] = useState(read);
  useEffect(() => {
    const update = () => setState(read());
    document.addEventListener("visibilitychange", update);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      document.removeEventListener("visibilitychange", update);
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  if (!state.online) return false;
  return state.hidden ? hiddenMs : focusedMs;
}

export const prefersReducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
