import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowLeft, CalendarPlus, Lock } from "lucide-react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { UserAvatar } from "@/components/app/UserAvatar";
import { Composer } from "./Composer";
import { MessageBubble } from "./MessageBubble";
import { useThread } from "./useThread";
import { dayKey, dayLabel, lastSeenLabel, prefersReducedMotion } from "./time";

const NEAR_BOTTOM_PX = 120;
const FLASH_MS = 1400;

/** Scroll a message to the middle of the message pane (never moves the page itself). */
function centerRow(scroller, row, smooth) {
  scroller.scrollTo({ top: row.offsetTop - (scroller.clientHeight - row.offsetHeight) / 2, behavior: smooth && !prefersReducedMotion() ? "smooth" : "auto" });
}

function statusLine(other) {
  if (!other) return { text: "", live: false };
  if (other.typing) return { text: "typing...", live: true };
  if (other.online) return { text: "online", live: true };
  if (other.lastActiveAt) return { text: lastSeenLabel(other.lastActiveAt), live: false };
  return { text: other.subtitle || "", live: false };
}

/** Right pane: header, messages on the dotted background, composer. Remounted (`key`) for every conversation. */
export function ThreadPane({ adapter, id, onBack, single }) {
  const qc = useQueryClient();
  const { query, data, pending, send, edit, unsend, hide, notifyTyping } = useThread(adapter, id);
  const other = data?.other;
  const name = other?.name || "Conversation";
  const status = statusLine(other);

  const [replyTo, setReplyTo] = useState(null);
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null); // message about to be unsent
  const [flashId, setFlashId] = useState(null);
  const [showJump, setShowJump] = useState(false);
  const [away, setAway] = useState(0); // new incoming messages while scrolled up
  const scroller = useRef(null);
  const stick = useRef(true);
  const lastSeen = useRef(null); // newest committed id already accounted for
  const flashTimer = useRef(null);

  // "N unread messages" divider: the list told us how many were unread when this conversation was opened.
  const [unreadAtOpen] = useState(() => (qc.getQueryData(adapter.listKey) || []).find((r) => String(r.id) === String(id))?.unread || 0);
  const [dividerId, setDividerId] = useState(null);
  const messages = useMemo(() => data?.messages || [], [data]);

  const items = useMemo(() => [...messages, ...pending], [messages, pending]);

  const scrollToEnd = useCallback((smooth = false) => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth && !prefersReducedMotion() ? "smooth" : "auto" });
  }, []);

  // Keep the view where the reader is: first load -> first unread (or the end); then follow new messages only when
  // already at the bottom (or when I sent them), otherwise count them on the jump button.
  useLayoutEffect(() => {
    if (!messages.length && !pending.length) return;
    const newest = messages.length ? messages[messages.length - 1].id : 0;
    if (lastSeen.current === null) {
      lastSeen.current = newest;
      let left = unreadAtOpen;
      let firstUnread = null;
      for (let i = messages.length - 1; i >= 0 && left > 0; i--) {
        if (!messages[i].is_mine && !messages[i].is_unsent && --left === 0) firstUnread = messages[i].id;
      }
      const row = firstUnread != null ? scroller.current?.querySelector(`[data-mid="${firstUnread}"]`) : null;
      if (row) { setDividerId(firstUnread); centerRow(scroller.current, row, false); stick.current = false; setShowJump(true); } else scrollToEnd();
      return;
    }
    const fresh = messages.filter((m) => m.id > lastSeen.current && !m.is_mine).length;
    lastSeen.current = Math.max(lastSeen.current, newest);
    const lastIsMine = pending.length > 0 || messages[messages.length - 1]?.is_mine;
    if (stick.current || lastIsMine) {
      scrollToEnd();
      stick.current = true;
      setAway(0);
      setShowJump(false);
    } else if (fresh) {
      setAway((n) => n + fresh);
      setShowJump(true);
    }
  }, [messages, pending.length, unreadAtOpen, scrollToEnd]);

  function onScroll() {
    const el = scroller.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    stick.current = near;
    setShowJump(!near);
    if (near) setAway(0);
  }

  const jumpTo = useCallback((messageId) => {
    const row = scroller.current?.querySelector(`[data-mid="${messageId}"]`);
    if (!row) return;
    centerRow(scroller.current, row, true);
    setFlashId(messageId);
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlashId(null), FLASH_MS);
  }, []);
  useEffect(() => () => clearTimeout(flashTimer.current), []);

  const startReply = useCallback((m) => { setEditing(null); setReplyTo(m); }, []);
  const startEdit = useCallback((m) => { setReplyTo(null); setEditing(m); }, []);
  const askUnsend = useCallback((m) => setConfirm(m), []);
  const doHide = useCallback((m) => { hide(m.id); }, [hide]);

  const closed = query.isError && !data;
  const link = adapter.headerLink?.(other);
  const avatars = other?.avatars || [{ name, src: other?.src }];

  return (
    <div className="wa-thread">
      <div className="wa-pane-header">
        {single ? null : (
          <button type="button" className="wa-icon-btn wa-back" onClick={onBack} aria-label="Back to conversations"><ArrowLeft aria-hidden="true" /></button>
        )}
        <div className="wa-header-main">
          <span className="wa-avatar-stack" aria-hidden="true">
            {avatars.map((a, i) => <UserAvatar key={i} name={a.name} src={a.src} size="md" className={avatars.length > 1 ? "ring-2 ring-[var(--wa-header)]" : undefined} />)}
          </span>
          <div className="wa-header-text">
            <span className="wa-header-name">{name}</span>
            <span className="wa-header-status" data-live={status.live || undefined} aria-live="polite">{status.text}</span>
          </div>
        </div>
        {link ? (
          <Link to={link.to} className="wa-icon-btn" aria-label={link.label} title={link.label}><CalendarPlus aria-hidden="true" /></Link>
        ) : null}
      </div>

      {closed ? (
        <div className="wa-placeholder" role="alert">
          <Lock aria-hidden="true" />
          <strong>{query.error?.isForbidden ? "This conversation is closed" : "Could not open this conversation"}</strong>
          <span>{query.error?.message}</span>
          {!query.error?.isForbidden && !query.error?.isNotFound ? <button type="button" className="wa-link" onClick={() => query.refetch()}>Try again</button> : null}
          <button type="button" className="wa-link" onClick={onBack}>Back to conversations</button>
        </div>
      ) : (
        <>
          {query.isError ? <p role="alert" className="m-0 bg-[var(--wa-header)] px-4 py-1 text-center text-xs text-[var(--wa-text-2)]">Connection problem - showing the last messages we received.</p> : null}
          <div ref={scroller} onScroll={onScroll} className="wa-scroller">
            {query.isPending ? (
              <div className="grid grid-cols-1 gap-3 px-6 py-2" role="status" aria-busy="true">
                <span className="sr-only">Loading messages</span>
                <Skeleton className="h-10 w-3/5 rounded-lg" />
                <Skeleton className="ml-auto h-10 w-1/2 rounded-lg" />
                <Skeleton className="h-14 w-2/3 rounded-lg" />
              </div>
            ) : items.length === 0 ? (
              <div className="wa-day"><span className="wa-note">{adapter.readOnly ? "No messages in this chat." : `No messages yet. Say hello to ${name}.`}</span></div>
            ) : (
              <ul role="log" aria-label={`Messages with ${name}`} className="wa-messages">
                {items.map((m, i) => {
                  const prev = items[i - 1];
                  const newDay = !prev || dayKey(prev.created_at) !== dayKey(m.created_at);
                  const first = newDay || prev.is_mine !== m.is_mine || (adapter.showSenderNames && prev.sender_name !== m.sender_name);
                  return (
                    <Fragment key={m.id}>
                      {newDay ? <li className="wa-day"><span>{dayLabel(m.created_at)}</span></li> : null}
                      {m.id === dividerId ? (
                        <li className="wa-day wa-unread-divider"><span>{unreadAtOpen} unread {unreadAtOpen === 1 ? "message" : "messages"}</span></li>
                      ) : null}
                      <MessageBubble
                        m={m}
                        first={first}
                        showName={!!adapter.showSenderNames}
                        flash={flashId === m.id}
                        otherName={name}
                        readOnly={adapter.readOnly}
                        pending={typeof m.id === "string"}
                        onReply={startReply}
                        onEdit={startEdit}
                        onUnsend={askUnsend}
                        onHide={doHide}
                        onJump={jumpTo}
                      />
                    </Fragment>
                  );
                })}
              </ul>
            )}
          </div>

          {showJump ? (
            <button type="button" className="wa-jump" onClick={() => { stick.current = true; scrollToEnd(true); setShowJump(false); setAway(0); }} aria-label={away ? `Scroll to the latest message, ${away} new` : "Scroll to the latest message"}>
              <ArrowDown aria-hidden="true" />
              {away ? <span className="wa-badge" aria-hidden="true">{away}</span> : null}
            </button>
          ) : null}

          {adapter.readOnly ? (
            <p className="wa-readonly m-0">Read-only view. Opening a conversation does not mark anything as seen.</p>
          ) : (
            <Composer
              canAttach={adapter.canAttach}
              disabled={query.isPending}
              placeholder="Type a message"
              replyTo={replyTo}
              onCancelReply={() => setReplyTo(null)}
              editing={editing}
              onCancelEdit={() => setEditing(null)}
              onTyping={notifyTyping}
              onSend={async ({ text, file }) => {
                const quote = replyTo;
                setReplyTo(null);
                try {
                  await send({ text, file, replyTo: quote });
                } catch (err) {
                  setReplyTo(quote);
                  throw err;
                }
              }}
              onSave={(text) => edit(editing.id, text)}
            />
          )}
        </>
      )}

      <AlertDialog open={!!confirm} onOpenChange={(o) => { if (!o) setConfirm(null); }}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Unsend message?</AlertDialogTitle>
            <AlertDialogDescription>It will be removed for everyone in this chat. They will see that you unsent a message.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => { const m = confirm; setConfirm(null); if (m) unsend(m.id); }}>Unsend</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
