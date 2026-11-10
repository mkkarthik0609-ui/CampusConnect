import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, errorMessage } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import { pollEvery } from "@/lib/polling";
import { usePollDelay } from "./time";

const TYPING_EVERY_MS = 3000;

/** Merge a poll result into the cached thread: new messages are added, changed ones (ticks, edit, unsend) replaced. */
function merge(prev, res) {
  const byId = new Map((prev?.messages || []).map((m) => [m.id, m]));
  for (const m of res.messages) byId.set(m.id, m);
  const messages = [...byId.values()].sort((a, b) => a.id - b.id);
  return { other: res.other, messages, lastId: Math.max(prev?.lastId || 0, res.lastId || 0), serverTime: res.serverTime };
}

/** The reply quote shown on an optimistic message (same shape as the server's `reply_to`). */
function quoteOf(m) {
  if (!m) return null;
  const kind = m.attachment ? (m.attachment.is_image ? "image" : "file") : null;
  return {
    id: m.id, is_mine: m.is_mine, sender_name: m.sender_name, unsent: false,
    text_preview: (m.message_text || "").slice(0, 120) || null, attachment_kind: kind, attachment_name: m.attachment?.name || null,
  };
}

/**
 * One conversation: adaptive polling (2.5 s focused, 12 s hidden tab, paused offline) that only asks for what is
 * new or changed (`after_id` + `updated_since`), optimistic sends, edit / unsend / delete-for-me, and a throttled
 * typing signal. Messages live in the react-query cache under `adapter.threadKey(id)`.
 */
export function useThread(adapter, id) {
  const qc = useQueryClient();
  const key = adapter.threadKey(id);
  const delay = usePollDelay(2500, false);
  const [pending, setPending] = useState([]);
  const lastTyping = useRef(0);

  const query = useQuery({
    queryKey: key,
    queryFn: async () => {
      const prev = qc.getQueryData(key);
      const res = await adapter.fetchThread(id, prev ? { afterId: prev.lastId, since: prev.serverTime } : {});
      return merge(prev, res);
    },
    // a closed / unknown conversation (4xx) is final: stop polling it
    refetchInterval: (q) => (q.state.error instanceof ApiError && q.state.error.status >= 400 && q.state.error.status < 500 ? false : pollEvery(delay, q)),
    refetchOnWindowFocus: true, // polling pauses while the tab is hidden
    staleTime: 0,
  });

  const patch = useCallback((fn) => qc.setQueryData(key, (old) => (old ? fn(old) : old)), [qc, key]);
  // Upserting a server item must NOT move `lastId`: a message from the other side may sit below it and be unfetched.
  const upsert = useCallback((item) => patch((old) => ({ ...old, messages: merge(old, { messages: [item], other: old.other }).messages })), [patch]);
  const refreshList = useCallback(() => {
    qc.invalidateQueries({ queryKey: adapter.listKey });
    qc.invalidateQueries({ queryKey: queryKeys.session });
  }, [qc, adapter.listKey]);

  const fail = useCallback((err, fallback) => {
    toast.error(errorMessage(err, fallback));
    if (err instanceof ApiError && (err.status === 409 || err.isForbidden)) qc.invalidateQueries({ queryKey: key });
  }, [qc, key]);

  /** Optimistic send. Resolves with the stored message; rejects (after a toast) when it failed so the composer can keep the draft. */
  const send = useCallback(async ({ text, file, replyTo }) => {
    const tmp = `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setPending((p) => [...p, {
      id: tmp, is_mine: true, status: "pending", message_text: text || null, is_edited: false, is_unsent: false, can_edit: false, can_unsend: false,
      attachment: file ? { name: file.name, url: null, is_image: false, type: file.name.split(".").pop() } : null,
      reply_to: quoteOf(replyTo), created_at: new Date().toISOString(),
    }]);
    try {
      const res = await adapter.send(id, { text, file, replyToId: replyTo?.id });
      upsert(res.item);
      refreshList();
      return res.item;
    } catch (err) {
      fail(err, "Your message was not sent.");
      throw err;
    } finally {
      setPending((p) => p.filter((m) => m.id !== tmp));
    }
  }, [adapter, id, upsert, refreshList, fail]);

  const edit = useCallback(async (messageId, text) => {
    try {
      upsert((await adapter.edit(messageId, text)).item);
      refreshList();
    } catch (err) {
      fail(err, "Could not edit that message.");
      throw err;
    }
  }, [adapter, upsert, refreshList, fail]);

  const unsend = useCallback(async (messageId) => {
    try {
      upsert((await adapter.unsend(messageId)).item);
      refreshList();
    } catch (err) {
      fail(err, "Could not unsend that message.");
    }
  }, [adapter, upsert, refreshList, fail]);

  const hide = useCallback(async (messageId) => {
    try {
      await adapter.hide(messageId);
      patch((old) => ({ ...old, messages: old.messages.filter((m) => m.id !== messageId) }));
      refreshList();
    } catch (err) {
      fail(err, "Could not delete that message.");
    }
  }, [adapter, patch, refreshList, fail]);

  /** Call on every keystroke: pings the server at most every 3 s. */
  const notifyTyping = useCallback(() => {
    if (adapter.readOnly || Date.now() - lastTyping.current < TYPING_EVERY_MS) return;
    lastTyping.current = Date.now();
    adapter.typing(id).catch(() => {});
  }, [adapter, id]);

  // Opening / polling a thread marks things seen: keep the list and the sidebar counter fresh.
  const data = query.data;
  const loaded = data !== undefined;
  const incoming = data ? data.messages.filter((m) => !m.is_mine).length : 0;
  useEffect(() => {
    if (!adapter.readOnly && loaded) refreshList();
  }, [incoming, loaded, adapter.readOnly, refreshList]);

  return { query, data, pending, send, edit, unsend, hide, notifyTyping };
}
