import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, ChevronRight, MessagesSquare } from "lucide-react";
import { PageHeader } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { ClassPath } from "@/components/app/ClassPath";
import { UserAvatar } from "@/components/app/UserAvatar";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { pluralize, timeAgo } from "@/lib/format";
import { ListSkeletonRows, QueryError, SearchBox, includesText } from "@/features/admin/common";

export default function AdminChats() {
  const q = useQuery({ queryKey: adminKeys.chats, queryFn: adminApi.chats });
  const [search, setSearch] = useState("");
  const items = useMemo(() => q.data?.items || [], [q.data]);
  const rows = useMemo(
    () => items.filter((c) => includesText(`${c.student.full_name} ${c.student.usn} ${c.faculty.full_name} ${c.faculty.faculty_code} ${c.last_message}`, search)),
    [items, search],
  );

  return (
    <>
      <PageHeader title="Chats" description="Every student and faculty conversation. You can read them, but not reply, and reading does not mark anything as seen." />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SearchBox value={search} onChange={setSearch} label="Search chats" placeholder="Student, faculty or last message" className="w-full sm:w-80" />
        {q.data ? <p className="m-0 text-sm text-muted-foreground" aria-live="polite">{rows.length} of {items.length} chats</p> : null}
      </div>

      {q.isPending ? <ListSkeletonRows rows={5} /> : null}
      {q.isError ? <QueryError error={q.error} onRetry={q.refetch} /> : null}
      {q.data && !rows.length ? (
        <div className="rounded-lg border bg-card shadow-sm"><EmptyState icon={MessagesSquare} title={items.length ? "No chats match" : "No conversations yet"}>{items.length ? "Try a different search." : "Chats start when a student or faculty member sends a first message."}</EmptyState></div>
      ) : null}

      {rows.length ? (
        <ul className="m-0 list-none overflow-hidden rounded-lg border bg-card p-0 shadow-sm">
          {rows.map((c) => (
            <li key={c.id} className="border-b border-line last:border-b-0">
              <Link to={`/admin/chats/${c.id}`} className="group flex items-center gap-3 px-4 py-3.5 text-inherit no-underline transition-colors hover:bg-primary-soft">
                <div className="flex shrink-0 -space-x-2" aria-hidden="true">
                  <UserAvatar name={c.student.full_name} src={c.student.profile_picture_url} size="sm" className="ring-2 ring-card" />
                  <UserAvatar name={c.faculty.full_name} src={c.faculty.profile_picture_url} size="sm" className="ring-2 ring-card" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 font-semibold">
                    <span>{c.student.full_name}</span>
                    <ArrowLeftRight aria-label="with" className="size-3.5 text-muted-foreground" />
                    <span>{c.faculty.full_name}</span>
                    <span className="font-mono text-[0.8125rem] font-normal text-muted-foreground">{c.student.usn} / {c.faculty.faculty_code}</span>
                  </div>
                  <p className="mt-0.5 mb-0 truncate text-sm text-muted-foreground">{c.last_message || "No messages yet"}</p>
                  {c.student.class ? <ClassPath cls={c.student.class} className="mt-1.5" /> : null}
                </div>
                <div className="shrink-0 text-right text-[0.8125rem] text-muted-foreground">
                  <div className="num">{pluralize(c.message_count, "message")}</div>
                  <div>{timeAgo(c.last_message_at || c.updated_at)}</div>
                </div>
                <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-muted-foreground max-sm:hidden" />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
