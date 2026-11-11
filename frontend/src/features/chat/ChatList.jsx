import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Ban, MessageSquarePlus, Paperclip, Search } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { UserAvatar } from "@/components/app/UserAvatar";
import { cn } from "@/lib/utils";
import { Tick } from "./MessageBubble";
import { listTime, usePollDelay } from "./time";
import { pollEvery } from "@/lib/polling";

/** Left pane: title, search box, All / Unread chips and the conversation rows. */
export function ChatList({ adapter, selectedId, onSelect }) {
  const delay = usePollDelay(5000, false);
  const query = useQuery({
    queryKey: adapter.listKey,
    queryFn: adapter.fetchList,
    refetchInterval: (q) => pollEvery(delay, q),
    refetchOnWindowFocus: true, // polling pauses while the tab is hidden
    staleTime: 2000,
  });
  const [search, setSearch] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);

  const rows = useMemo(() => query.data || [], [query.data]);
  const unreadTotal = rows.reduce((n, r) => n + (r.unread > 0 ? 1 : 0), 0);
  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (unreadOnly && !r.unread) return false;
      return !needle || `${r.name} ${r.subtitle || ""} ${r.preview || ""}`.toLowerCase().includes(needle);
    });
  }, [rows, search, unreadOnly]);

  return (
    <>
      <div className="wa-pane-header">
        <h2 className="wa-title">{adapter.title}</h2>
        {adapter.newChat ? (
          <Link to={adapter.newChat.to} className="wa-icon-btn" aria-label={adapter.newChat.label} title={adapter.newChat.label}>
            <MessageSquarePlus aria-hidden="true" />
          </Link>
        ) : null}
      </div>
      <div className="wa-search" role="search">
        <label>
          <span className="sr-only">Search conversations</span>
          <Search aria-hidden="true" />
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search or start a new chat" />
        </label>
      </div>
      <div className="wa-chips" role="group" aria-label="Filter conversations">
        <button type="button" className="wa-chip-btn" aria-pressed={!unreadOnly} onClick={() => setUnreadOnly(false)}>All</button>
        <button type="button" className="wa-chip-btn" aria-pressed={unreadOnly} onClick={() => setUnreadOnly(true)}>
          Unread{unreadTotal ? ` ${unreadTotal}` : ""}
        </button>
      </div>

      {query.isPending ? (
        <div className="grid grid-cols-1 gap-3 p-4" role="status" aria-busy="true">
          <span className="sr-only">Loading conversations</span>
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}
        </div>
      ) : query.isError ? (
        <div className="wa-empty-list" role="alert">
          <p className="m-0">Could not load your conversations.</p>
          <button type="button" className="wa-link" onClick={() => query.refetch()}>Try again</button>
        </div>
      ) : shown.length === 0 ? (
        <div className="wa-empty-list">
          <p className="m-0">{rows.length === 0 ? adapter.emptyText : unreadOnly && !search ? "No unread conversations." : "No conversations match your search."}</p>
          {rows.length === 0 && adapter.newChat ? <Link to={adapter.newChat.to}>{adapter.newChat.label}</Link> : null}
        </div>
      ) : (
        <ul className="wa-chat-list" aria-label="Conversations">
          {shown.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                className="wa-chat"
                aria-current={String(r.id) === String(selectedId) ? "true" : undefined}
                data-unread={r.unread > 0 || undefined}
                onClick={() => onSelect(r.id)}
              >
                <span className="wa-avatar-stack" aria-hidden="true">
                  {(r.avatars || [{ name: r.name, src: r.src }]).map((a, i) => (
                    <UserAvatar key={i} name={a.name} src={a.src} size="md" className={cn(r.avatars && "ring-2 ring-[var(--wa-panel)]")} />
                  ))}
                </span>
                <span className="wa-chat-body">
                  <span className="wa-chat-top">
                    <span className="wa-chat-name">{r.name}</span>
                    {r.time ? <time className="wa-chat-time" dateTime={r.time}>{listTime(r.time)}</time> : null}
                  </span>
                  <span className="wa-chat-bottom">
                    <span className="wa-chat-preview">
                      {r.typing ? (
                        <span className="wa-typing-text">typing...</span>
                      ) : (
                        <>
                          {r.mine && r.status && !r.unsent ? <Tick status={r.status} /> : null}
                          {r.unsent ? <Ban aria-hidden="true" /> : r.attachment ? <Paperclip aria-hidden="true" /> : null}
                          <span style={r.unsent ? { fontStyle: "italic" } : undefined}>{r.preview || r.subtitle || "No messages yet"}</span>
                        </>
                      )}
                    </span>
                    {r.unread > 0 ? (
                      <span className="wa-badge">{r.unread}<span className="sr-only"> unread {r.unread === 1 ? "message" : "messages"}</span></span>
                    ) : null}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
