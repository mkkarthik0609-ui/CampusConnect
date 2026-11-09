import { ChatListView } from "./ChatListView";

/** /student/chat/:id and /faculty/chat/:id: the same two-pane screen with that conversation open. */
export function ChatThreadView({ role }) {
  return <ChatListView role={role} />;
}
