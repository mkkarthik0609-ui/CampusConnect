import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail, Send } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { Notice } from "@/components/app/Notice";
import { SubmitButton } from "@/components/app/SubmitButton";
import { adminApi, adminMessagesApi } from "@/lib/endpoints";
import { formatDateTime } from "@/lib/format";
import { errorMessage } from "@/lib/api";
import { toast } from "sonner";

export default function AdminMessages() {
  const { role } = useAuth();
  const isAdmin = role === "ADMIN";
  const faculty = useQuery({ queryKey: ["admin", "faculty"], queryFn: adminApi.faculty, enabled: isAdmin });
  const [selected, setSelected] = useState("");
  const [text, setText] = useState("");
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["admin-messages", isAdmin, selected],
    queryFn: () => (isAdmin && selected ? adminMessagesApi.thread(selected) : adminMessagesApi.list()),
    enabled: !isAdmin || Boolean(selected),
    refetchInterval: 10000,
  });
  const people = useMemo(() => faculty.data?.items || [], [faculty.data]);

  useEffect(() => {
    if (isAdmin && !selected && people.length) setSelected(String(people[0].user_id));
  }, [isAdmin, people, selected]);

  const send = useMutation({
    mutationFn: () => adminMessagesApi.send({ message_text: text, ...(isAdmin ? { recipient_user_id: Number(selected) } : {}) }),
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: ["admin-messages"] });
      toast.success("Message sent.");
    },
    onError: (err) => toast.error(errorMessage(err)),
  });
  const messages = list.data?.items || [];
  const selectedFaculty = people.find((f) => String(f.user_id) === String(selected));

  return (
    <>
      <PageHeader
        title={isAdmin ? "Faculty messages" : "Message Admin"}
        description={isAdmin ? "Read and reply to faculty messages, or start a message with any faculty member." : "Send a private message to the Campus Connect admin."}
      />
      {isAdmin ? (
        <label className="mb-4 block max-w-md text-sm font-semibold">
          Faculty member
          <select value={selected} onChange={(e) => setSelected(e.target.value)} className="mt-1.5 flex h-10 w-full rounded-md border border-input bg-surface px-3 text-sm">
            {people.map((f) => <option key={f.user_id} value={f.user_id}>{f.full_name} ({f.faculty_code})</option>)}
          </select>
        </label>
      ) : null}
      {list.isError ? <Notice tone="danger" title="Could not load messages">{list.error.message}</Notice> : null}
      <section className="grid max-w-3xl gap-4">
        <div className="overflow-hidden rounded-lg border border-line bg-card shadow-sm">
          {messages.length ? (
            <ol className="m-0 list-none divide-y divide-line p-0">
            {messages.map((m) => {
              return (
                  <li key={m.id} className="grid gap-1 px-4 py-3.5">
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="font-semibold">{m.sender.name} <span className="font-normal text-muted-foreground">({m.sender.role.toLowerCase()})</span></span>
                      <span className="text-muted-foreground">{formatDateTime(m.created_at)}</span>
                    </div>
                    <p className="m-0 whitespace-pre-wrap text-sm">{m.message_text}</p>
                  </li>
                );
              })}
            </ol>
          ) : (
            <EmptyState icon={Mail} title={isAdmin && selectedFaculty ? `No messages with ${selectedFaculty.full_name}` : "No messages yet"} />
          )}
        </div>
        <form
          className="grid gap-3 rounded-lg border border-line bg-card p-4 shadow-sm"
          onSubmit={(e) => { e.preventDefault(); if (text.trim() && (!isAdmin || selected)) send.mutate(); }}
        >
          <label htmlFor="admin-message" className="text-sm font-semibold">Message</label>
          <Textarea id="admin-message" value={text} onChange={(e) => setText(e.target.value)} maxLength={5000} placeholder={isAdmin ? "Write a reply or new message..." : "Write your message to the admin..."} />
          <div className="flex justify-end">
            <SubmitButton type="submit" loading={send.isPending} disabled={!text.trim() || (isAdmin && !selected)}>
              <Send aria-hidden="true" /> Send message
            </SubmitButton>
          </div>
        </form>
      </section>
    </>
  );
}
