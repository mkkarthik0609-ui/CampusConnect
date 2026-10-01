import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { MessagesSquare, Paperclip, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { ListSkeleton } from "@/components/app/PageLoader";
import { Notice } from "@/components/app/Notice";
import { UserAvatar } from "@/components/app/UserAvatar";
import { ClassPath } from "@/components/app/ClassPath";
import { chatApi } from "@/lib/endpoints";
import { formatDateTime, timeAgo } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";
import { cn } from "@/lib/utils";

/** Mentor-Connect inbox, shared by both roles (`role` = "STUDENT" | "FACULTY"). */
export function ChatListView({ role }) {
  const student = role === "STUDENT";
  const base = student ? "/student" : "/faculty";
  const query = useQuery({ queryKey: queryKeys.chats, queryFn: chatApi.list, refetchInterval: 15_000, staleTime: 5_000 });
  const items = query.data?.items || [];

  return (
    <>
      <PageHeader
        title="Mentor-Connect"
        description={student ? "Your conversations with faculty." : "Your conversations with students."}
        actions={
          <Button asChild variant="outline">
            <Link to={student ? "/student/find-faculty" : "/faculty/find-students"}>
              <Search aria-hidden="true" /> {student ? "Find faculty" : "Find a student"}
            </Link>
          </Button>
        }
      />

      <div className="overflow-hidden rounded-lg border border-line bg-card shadow-sm">
        {query.isPending ? (
          <ListSkeleton rows={4} className="p-3" />
        ) : query.isError ? (
          <div className="p-3">
            <Notice tone="danger" title="Could not load your conversations">
              {query.error.message}
              <Button variant="outline" size="sm" className="mt-2" onClick={() => query.refetch()}>Try again</Button>
            </Notice>
          </div>
        ) : items.length === 0 ? (
          <EmptyState icon={MessagesSquare} title="No conversations yet">
            {student ? (
              <p>Message the faculty assigned to your class from your dashboard, or find a faculty member who can support you.</p>
            ) : (
              <p>Open a student from one of your classes, or search for a student, to start a conversation.</p>
            )}
            <div className="flex flex-wrap justify-center gap-2">
              <Button asChild><Link to={`${base}/${student ? "dashboard" : "classes"}`}>{student ? "Go to dashboard" : "Open my classes"}</Link></Button>
              <Button asChild variant="outline"><Link to={student ? "/student/find-faculty" : "/faculty/find-students"}>{student ? "Find faculty" : "Find a student"}</Link></Button>
            </div>
          </EmptyState>
        ) : (
          <ul className="m-0 list-none p-0">
            {items.map((c) => {
              const o = c.other;
              const unread = c.unread_count > 0;
              return (
                <li key={c.chat_id} className="border-t border-line first:border-t-0">
                  <Link
                    to={`${base}/chat/${c.chat_id}`}
                    className={cn(
                      "flex items-center gap-3.5 px-[clamp(0.85rem,2.5vw,1.25rem)] py-3.5 text-inherit no-underline outline-none transition-colors hover:bg-primary-soft focus-visible:bg-primary-soft focus-visible:ring-[3px] focus-visible:ring-inset focus-visible:ring-ring/60",
                      unread && "bg-primary-soft/50",
                    )}
                  >
                    <UserAvatar name={o.full_name} src={o.profile_picture_url} size="md" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-3">
                        <p className={cn("m-0 min-w-0 truncate", unread ? "font-bold" : "font-[650]")}>
                          {o.full_name}
                          <span className="ml-2 font-mono text-[0.8125rem] font-medium text-muted-foreground">{o.code}</span>
                        </p>
                        {c.last_message_at ? (
                          <time dateTime={c.last_message_at} title={formatDateTime(c.last_message_at)} className="shrink-0 text-[0.8125rem] text-muted-foreground tabular-nums">
                            {timeAgo(c.last_message_at)}
                          </time>
                        ) : null}
                      </div>
                      {!student && o.class ? <ClassPath cls={o.class} className="mt-0.5 text-[0.75rem]" /> : null}
                      <div className="mt-0.5 flex items-center gap-2">
                        <p className={cn("m-0 min-w-0 flex-1 truncate text-[0.9375rem]", unread ? "font-semibold text-foreground" : "text-muted-foreground")}>
                          {c.last_message ? (
                            <>
                              {c.last_message_is_mine ? <span className="text-muted-foreground">You: </span> : null}
                              {c.last_message.startsWith("Attachment:") ? <Paperclip aria-hidden="true" className="mr-1 inline size-3.5 align-[-2px]" /> : null}
                              {c.last_message}
                            </>
                          ) : (
                            "No messages yet"
                          )}
                        </p>
                        {unread ? (
                          <span className="inline-flex min-w-6 shrink-0 items-center justify-center rounded-full bg-saffron px-1.5 py-0.5 text-xs font-bold text-on-saffron tabular-nums">
                            {c.unread_count}
                            <span className="sr-only"> unread {c.unread_count === 1 ? "message" : "messages"}</span>
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}
