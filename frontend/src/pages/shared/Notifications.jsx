import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { ListSkeleton } from "@/components/app/PageLoader";
import { Notice } from "@/components/app/Notice";
import { useAuth } from "@/auth/AuthProvider";
import { notificationsApi } from "@/lib/endpoints";
import { queryKeys } from "@/lib/queryClient";
import { errorMessage } from "@/lib/api";
import { formatDateTime, timeAgo } from "@/lib/format";
import { notificationTarget } from "@/lib/notificationTarget";
import { cn } from "@/lib/utils";

/** /notifications - requests, replies and reminders addressed to the signed-in user. */
export default function Notifications() {
  const qc = useQueryClient();
  const { role } = useAuth();
  const query = useQuery({ queryKey: queryKeys.notifications, queryFn: notificationsApi.list, refetchInterval: 30_000 });

  const refreshCounts = () => {
    qc.invalidateQueries({ queryKey: queryKeys.notifications });
    qc.invalidateQueries({ queryKey: queryKeys.session }); // updates the sidebar badge
  };

  const markRead = useMutation({
    mutationFn: notificationsApi.markRead,
    onSuccess: refreshCounts,
    onError: (err) => toast.error(errorMessage(err, "Could not mark that notification as read.")),
  });
  const markAll = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: () => { toast.success("All notifications marked as read."); refreshCounts(); },
    onError: (err) => toast.error(errorMessage(err, "Could not mark notifications as read.")),
  });

  const items = query.data?.items || [];
  const unread = query.data?.unread_count ?? items.filter((n) => !n.is_read).length;

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Requests, replies and reminders addressed to you."
        actions={
          items.length && unread ? (
            <Button variant="outline" onClick={() => markAll.mutate()} disabled={markAll.isPending}>
              <CheckCheck aria-hidden="true" /> Mark all read
            </Button>
          ) : null
        }
      />

      <div className="rounded-lg border bg-card p-[clamp(0.5rem,1.5vw,1rem)] shadow-sm">
        {query.isPending ? (
          <ListSkeleton rows={4} className="p-2" />
        ) : query.isError ? (
          <Notice tone="danger" title="Could not load your notifications">
            {query.error.message}
            <Button variant="outline" size="sm" className="mt-2" onClick={() => query.refetch()}>Try again</Button>
          </Notice>
        ) : items.length === 0 ? (
          <EmptyState icon={Bell} title="You're all caught up">
            <p>Meeting replies, new messages and approval decisions will appear here.</p>
          </EmptyState>
        ) : (
          <ul className="m-0 list-none p-0">
            {items.map((n) => {
              const target = notificationTarget(n, role);
              const open = () => { if (!n.is_read) markRead.mutate(n.id); };
              return (
                <li
                  key={n.id}
                  className={cn(
                    "flex items-start gap-3 border-t border-line px-2 py-3.5 first:border-t-0",
                    !n.is_read && "my-0.5 rounded-lg border-t-transparent bg-primary-soft px-3.5",
                    !n.is_read && "[&+li]:border-t-transparent",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn("mt-2 size-2.5 shrink-0 rounded-full", n.is_read ? "shadow-[inset_0_0_0_2px_var(--line-strong)]" : "bg-saffron")}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="m-0 font-[650]">
                      {!n.is_read ? <span className="sr-only">Unread: </span> : null}
                      {target ? (
                        <Link to={target} onClick={open} className="text-inherit no-underline hover:text-primary hover:underline">{n.title}</Link>
                      ) : n.title}
                    </p>
                    <p className="m-0 mt-0.5 text-[0.9688rem] text-ink-2">{n.message}</p>
                    <time dateTime={n.created_at} title={formatDateTime(n.created_at)} className="mt-1 block text-[0.8125rem] text-muted-foreground tabular-nums">
                      {timeAgo(n.created_at)}
                    </time>
                  </div>
                  {!n.is_read ? (
                    <Button variant="secondary" size="sm" onClick={() => markRead.mutate(n.id)} disabled={markRead.isPending && markRead.variables === n.id}>
                      Mark read
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}
