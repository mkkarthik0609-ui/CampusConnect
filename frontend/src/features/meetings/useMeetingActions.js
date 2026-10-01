import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { errorMessage } from "@/lib/api";
import { meetingsApi } from "@/lib/endpoints";
import { queryKeys } from "@/lib/queryClient";

/** Status filter tabs, in the order people think about a request's life. */
export const MEETING_TABS = [
  { value: "all", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "accepted", label: "Accepted" },
  { value: "completed", label: "Completed" },
  { value: "rejected", label: "Rejected" },
  { value: "cancelled", label: "Cancelled" },
];

/** Refresh everything a meeting change touches (list, dashboards, notification counters). */
export function useRefreshMeetings() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: queryKeys.meetings });
    qc.invalidateQueries({ queryKey: queryKeys.studentDashboard });
    qc.invalidateQueries({ queryKey: ["faculty"] });
    qc.invalidateQueries({ queryKey: queryKeys.session });
  };
}

/** respond / cancel / complete mutations. Errors are thrown on so dialogs can show them inline; they also toast. */
export function useMeetingActions() {
  const refresh = useRefreshMeetings();

  const respond = useMutation({
    mutationFn: ({ id, ...body }) => meetingsApi.respond(id, body),
    onSuccess: (res) => { toast.success(res.message || "Response sent."); refresh(); },
    onError: (err) => { toast.error(errorMessage(err)); refresh(); },
  });
  const cancel = useMutation({
    mutationFn: ({ id, reason }) => meetingsApi.cancel(id, reason),
    onSuccess: (res) => { toast.success(res.message || "Meeting cancelled."); refresh(); },
    onError: () => refresh(),
  });
  const complete = useMutation({
    mutationFn: (id) => meetingsApi.complete(id),
    onSuccess: (res) => { toast.success(res.message || "Meeting marked completed."); refresh(); },
    onError: () => refresh(),
  });
  return { respond, cancel, complete };
}
