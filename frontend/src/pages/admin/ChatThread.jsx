import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check, CheckCheck, Eye, FileText, Paperclip } from "lucide-react";
import { PageHeader } from "@/components/app/PageHeader";
import { PageLoader } from "@/components/app/PageLoader";
import { ClassPath } from "@/components/app/ClassPath";
import { EmptyState } from "@/components/app/EmptyState";
import { Notice } from "@/components/app/Notice";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { uploadUrl } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { QueryError } from "@/features/admin/common";
import { cn } from "@/lib/utils";

function Attachment({ m }) {
  if (!m.attachment_url) return null;
  const href = uploadUrl(m.attachment_url);
  const isImage = (m.attachment_type || "").startsWith("image");
  return (
    <a href={href} target="_blank" rel="noreferrer" className="mt-1.5 flex items-center gap-2 rounded-md border border-line bg-surface-2 p-2 text-sm font-semibold text-primary no-underline hover:border-primary">
      {isImage ? <img src={href} alt={m.attachment_name || "Attachment"} className="max-h-40 rounded" /> : (
        <>
          <FileText aria-hidden="true" className="size-4 shrink-0" />
          <span className="truncate">{m.attachment_name || "Attachment"}</span>
        </>
      )}
    </a>
  );
}

export default function AdminChatThread() {
  const { id } = useParams();
  const q = useQuery({ queryKey: adminKeys.chat(id), queryFn: () => adminApi.chat(id) });

  if (q.isPending) return <PageLoader />;
  if (q.isError) {
    return (
      <>
        <PageHeader title="Chat" back={{ to: "/admin/chats", label: "All chats" }} />
        <QueryError error={q.error} onRetry={q.refetch} />
      </>
    );
  }
  const { chat, messages } = q.data;

  return (
    <>
      <PageHeader
        title={`${chat.student.full_name} and ${chat.faculty.full_name}`}
        back={{ to: "/admin/chats", label: "All chats" }}
        description={`Student ${chat.student.usn}, faculty ${chat.faculty.faculty_code}. ${chat.message_count} ${chat.message_count === 1 ? "message" : "messages"}.`}
        actions={chat.student.class ? <ClassPath cls={chat.student.class} /> : null}
      />
      <Notice tone="info" icon={Eye} className="mb-4" title="Read-only view">
        Messages are not marked as seen when you open this page.
      </Notice>

      <div className="rounded-lg border bg-card shadow-sm">
        {messages.length ? (
          <ol aria-label="Messages, oldest first" className="m-0 flex list-none flex-col gap-3 p-4 sm:p-5">
            {messages.map((m) => {
              const fromFaculty = m.sender_role === "FACULTY";
              return (
                <li key={m.id} className={cn("flex flex-col", fromFaculty ? "items-end" : "items-start")}>
                  <span className="mb-0.5 px-1 text-[0.8125rem] text-muted-foreground">
                    <span className="font-semibold text-ink-2">{m.sender_name}</span> ({fromFaculty ? "faculty" : "student"})
                  </span>
                  <div className={cn("bubble", fromFaculty ? "bubble-mine" : "bubble-theirs")}>
                    {m.message_text ? <p className="m-0 whitespace-pre-wrap">{m.message_text}</p> : null}
                    <Attachment m={m} />
                  </div>
                  <span className="num mt-0.5 flex items-center gap-1.5 px-1 text-xs text-muted-foreground">
                    {formatDateTime(m.created_at)}
                    {m.is_edited ? <span>edited</span> : null}
                    {m.attachment_url && !m.attachment_name ? <Paperclip aria-label="has attachment" className="size-3" /> : null}
                    {m.is_seen ? <span className="inline-flex items-center gap-0.5"><CheckCheck aria-hidden="true" className="size-3.5" />Seen</span> : <span className="inline-flex items-center gap-0.5"><Check aria-hidden="true" className="size-3.5" />Sent</span>}
                  </span>
                </li>
              );
            })}
          </ol>
        ) : <EmptyState title="No messages in this chat" />}
      </div>
    </>
  );
}
