import { useCallback, useEffect } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { MessagesSquare } from "lucide-react";
import { usePageTitle } from "@/hooks/usePageTitle";
import { ChatList } from "./ChatList";
import { ThreadPane } from "./ThreadPane";
import "./chat.css";

/**
 * The shared messaging screen (WhatsApp Web layout): conversation list on the left, thread on the right; on a phone
 * only one of them at a time (the thread has a back arrow). Which conversation is open comes from the URL:
 * `/:id` for `adapter.selectBy === "param"`, `?c=` for "query". Every surface is described by an adapter (adapters.js).
 */
export function ChatPage({ adapter }) {
  const { id: paramId } = useParams();
  const [search, setSearch] = useSearchParams();
  const navigate = useNavigate();
  usePageTitle(adapter.title);

  const byQuery = adapter.selectBy === "query";
  const selectedId = byQuery ? search.get("c") : paramId;

  const select = useCallback((id, replace = false) => {
    if (byQuery) setSearch({ c: String(id) }, { replace });
    else navigate(`${adapter.basePath}/${id}`, { replace });
  }, [adapter.basePath, byQuery, navigate, setSearch]);
  const back = useCallback(() => {
    if (byQuery) setSearch({}); else navigate(adapter.basePath);
  }, [adapter.basePath, byQuery, navigate, setSearch]);

  // Faculty have exactly one admin conversation: open it straight away.
  const list = useQuery({ queryKey: adapter.listKey, queryFn: adapter.fetchList, enabled: !!adapter.autoOpenSingle, staleTime: 2000 });
  const only = adapter.autoOpenSingle && list.data?.length === 1 ? list.data[0].id : null;
  useEffect(() => {
    if (only != null && !selectedId) select(only, true);
  }, [only, selectedId, select]);

  return (
    <>
      <h1 className="sr-only">{adapter.title}</h1>
      <div className="wa-shell" data-view={selectedId ? "thread" : "list"}>
        <section className="wa-list-pane" aria-label="Conversations">
          <ChatList adapter={adapter} selectedId={selectedId} onSelect={select} />
        </section>
        <section className="wa-thread-pane" aria-label="Conversation">
          {selectedId ? (
            <ThreadPane key={selectedId} adapter={adapter} id={selectedId} onBack={back} single={only != null} />
          ) : (
            <div className="wa-placeholder">
              <MessagesSquare aria-hidden="true" />
              <strong>{adapter.title}</strong>
              <span>Select a conversation to read and send messages.</span>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
