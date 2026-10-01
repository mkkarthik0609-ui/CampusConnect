import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, CalendarPlus, MessageSquareText } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/app/PageHeader";
import { ClassPath } from "@/components/app/ClassPath";
import { Notice } from "@/components/app/Notice";
import { UserAvatar } from "@/components/app/UserAvatar";
import { ApiError, errorMessage } from "@/lib/api";
import { chatApi } from "@/lib/endpoints";
import { parseApiDate } from "@/lib/format";
import { queryKeys } from "@/lib/queryClient";
import { Composer } from "./Composer";
import { MessageBubble } from "./MessageBubble";

const POLL_MS = 5000;
const NEAR_BOTTOM_PX = 140;

const dayFmt = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "short" });
function dayLabel(value) {
  const d = parseApiDate(value) || new Date();
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86400000);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return dayFmt.format(d);
}
const dayKey = (value) => (parseApiDate(value) || new Date()).toDateString();

/**
 * One conversation, shared by both roles (`role` = "STUDENT" | "FACULTY").
 * Polls every 5 s while open (paused when the tab is hidden), sends text optimistically, uploads files,
 * lets you edit your own unseen text messages and keeps the view pinned to the newest message.
 */
export function ChatThreadView({ role }) {
  const { id } = useParams();
  const qc = useQueryClient();
  const base = role === "STUDENT" ? "/student" : "/faculty";
  const key = queryKeys.chat(id);

  const query = useQuery({
    queryKey: key,
    queryFn: () => chatApi.get(id),
    refetchInterval: (q) => (q.state.error instanceof ApiError && q.state.error.status < 500 && q.state.error.status > 0 ? false : POLL_MS),
    refetchOnWindowFocus: true,
    staleTime: 0,
  });

  const [pending, setPending] = useState([]); // optimistic text messages
  const [editingId, setEditingId] = useState(null);
  const scroller = useRef(null);
  const stick = useRef(true);
  const [showJump, setShowJump] = useState(false);

  const messages = useMemo(() => query.data?.messages || [], [query.data]);
  const other = query.data?.chat?.other;

  // Fetching a thread marks its incoming messages as seen: refresh the sidebar counter and the list.
  const lastId = query.data?.last_id;
  useEffect(() => {
    if (lastId === undefined) return;
    qc.invalidateQueries({ queryKey: queryKeys.session });
    qc.invalidateQueries({ queryKey: queryKeys.chats });
  }, [lastId, qc]);

  const scrollToEnd = useCallback((smooth = false) => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }, []);

  const count = messages.length + pending.length;
  const lastIsMine = pending.length > 0 || messages[messages.length - 1]?.is_mine;
  useLayoutEffect(() => {
    if (stick.current || lastIsMine) {
      scrollToEnd();
      stick.current = true;
      setShowJump(false);
    } else if (count) {
      setShowJump(true);
    }
  }, [count, lastIsMine, scrollToEnd]);

  function onScroll() {
    const el = scroller.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    stick.current = near;
    if (near) setShowJump(false);
  }

  const send = useMutation({
    mutationFn: ({ text, file }) => chatApi.send(id, { text, file }),
    onMutate: async ({ text, file, tmpId }) => {
      if (file) return;
      setPending((p) => [...p, { id: tmpId, is_mine: true, message_text: text, attachment: null, is_seen: false, is_edited: false, can_edit: false, created_at: new Date().toISOString() }]);
    },
    onSuccess: async (res, vars) => {
      await qc.cancelQueries({ queryKey: key });
      qc.setQueryData(key, (old) => {
        if (!old || !res?.item) return old;
        if (old.messages.some((m) => m.id === res.item.id)) return old;
        return { ...old, messages: [...old.messages, res.item], last_id: res.item.id };
      });
      setPending((p) => p.filter((m) => m.id !== vars.tmpId));
      qc.invalidateQueries({ queryKey: queryKeys.chats });
    },
    onError: (err, vars) => {
      setPending((p) => p.filter((m) => m.id !== vars.tmpId));
      toast.error(errorMessage(err, "Your message was not sent."));
      if (err instanceof ApiError && err.isForbidden) qc.invalidateQueries({ queryKey: key });
    },
  });

  const handleSend = ({ text, file }) => send.mutateAsync({ text, file, tmpId: `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}` });

  const edit = useMutation({
    mutationFn: ({ messageId, text }) => chatApi.edit(messageId, text),
    onSuccess: (res) => {
      qc.setQueryData(key, (old) => (old ? { ...old, messages: old.messages.map((m) => (m.id === res.item.id ? res.item : m)) } : old));
      setEditingId(null);
      toast.success("Message updated.");
    },
    onError: (err) => {
      toast.error(errorMessage(err, "Could not edit that message."));
      if (err instanceof ApiError && (err.status === 409 || err.isForbidden)) {
        setEditingId(null);
        qc.invalidateQueries({ queryKey: key });
      }
    },
  });

  const name = other?.full_name || "Conversation";
  const items = [...messages, ...pending];

  // The class path / ID line under the title
  let description = null;
  if (other?.role === "STUDENT") {
    description = (
      <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-mono text-[0.875rem]">{other.usn}</span>
        <ClassPath cls={other.class} />
      </span>
    );
  } else if (other) {
    description = (
      <span>
        <span className="font-mono text-[0.875rem]">{other.faculty_code}</span>
        {other.department ? <span> - {other.department}</span> : null}
      </span>
    );
  }

  return (
    <>
      <PageHeader
        title={
          <span className="inline-flex items-center gap-3">
            {other ? <UserAvatar name={other.full_name} src={other.profile_picture_url} size="md" /> : null}
            <span className="min-w-0 break-words">{name}</span>
          </span>
        }
        documentTitle={other ? `${name} - Mentor-Connect` : "Mentor-Connect"}
        description={description}
        back={{ to: `${base}/chat`, label: "All conversations" }}
        actions={
          role === "STUDENT" && other?.id ? (
            <Button asChild variant="outline">
              <Link to={`/student/meetings/request/${other.id}`}>
                <CalendarPlus aria-hidden="true" /> Request meeting
              </Link>
            </Button>
          ) : null
        }
      />

      {query.isError && !query.data ? (
        <Notice tone={query.error?.isForbidden ? "warning" : "danger"} title={query.error?.isForbidden ? "This conversation is closed" : "Could not open this conversation"}>
          {query.error?.message}
          <div className="mt-2 flex gap-2">
            <Button asChild variant="outline" size="sm"><Link to={`${base}/chat`}>Back to conversations</Link></Button>
            {!query.error?.isForbidden && !query.error?.isNotFound ? <Button variant="outline" size="sm" onClick={() => query.refetch()}>Try again</Button> : null}
          </div>
        </Notice>
      ) : (
        <section aria-label={`Conversation with ${name}`} className="relative flex h-[clamp(22rem,calc(100dvh-16rem),46rem)] flex-col overflow-hidden rounded-lg border border-line bg-card shadow-sm">
          {query.isError ? (
            <p role="alert" className="m-0 border-b border-warn-line bg-warn px-4 py-1.5 text-sm font-semibold text-warn-ink">
              Connection problem - showing the last messages we received.
            </p>
          ) : null}
          <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto bg-sunken/60 px-[clamp(0.75rem,2.5vw,1.5rem)] py-4">
            {query.isPending ? (
              <div className="grid gap-3" role="status" aria-busy="true">
                <span className="sr-only">Loading messages</span>
                <Skeleton className="h-12 w-3/5 rounded-2xl" />
                <Skeleton className="ml-auto h-12 w-1/2 rounded-2xl" />
                <Skeleton className="h-16 w-2/3 rounded-2xl" />
              </div>
            ) : items.length === 0 ? (
              <div className="grid h-full place-content-center justify-items-center gap-2 text-center text-muted-foreground">
                <MessageSquareText aria-hidden="true" className="size-9 text-primary-ink" />
                <p className="m-0 font-semibold text-ink-2">No messages yet</p>
                <p className="m-0 max-w-[30ch] text-sm">Say hello to {name} to start the conversation.</p>
              </div>
            ) : (
              <ul role="log" aria-label={`Messages with ${name}`} className="m-0 grid list-none gap-1.5 p-0">
                {items.map((m, i) => {
                  const prev = items[i - 1];
                  const newDay = !prev || dayKey(prev.created_at) !== dayKey(m.created_at);
                  const isPending = typeof m.id === "string";
                  return (
                    <Fragment key={m.id}>
                      {newDay ? (
                        <li className="my-2 flex justify-center" aria-hidden="false">
                          <span className="rounded-full bg-card px-3 py-0.5 text-xs font-semibold text-muted-foreground shadow-xs">{dayLabel(m.created_at)}</span>
                        </li>
                      ) : null}
                      <MessageBubble
                        message={m}
                        otherName={name}
                        pending={isPending}
                        editing={editingId === m.id}
                        saving={edit.isPending}
                        onEdit={() => setEditingId(m.id)}
                        onCancelEdit={() => setEditingId(null)}
                        onSaveEdit={(text) => edit.mutate({ messageId: m.id, text })}
                      />
                    </Fragment>
                  );
                })}
              </ul>
            )}
          </div>

          {showJump ? (
            <Button
              type="button"
              size="sm"
              variant="default"
              className="absolute right-4 bottom-[5.25rem] rounded-full shadow-md"
              onClick={() => { stick.current = true; scrollToEnd(true); setShowJump(false); }}
            >
              <ArrowDown aria-hidden="true" /> New messages
            </Button>
          ) : null}

          <Composer onSend={handleSend} disabled={query.isPending || (query.isError && !query.data)} placeholder={`Message ${name}`} />
        </section>
      )}
    </>
  );
}
