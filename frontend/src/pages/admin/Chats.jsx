import { ChatPage } from "@/features/chat/ChatShell";
import { adminChatsAdapter } from "@/features/chat/adapters";

/** Admin: read-only viewer of every student/faculty conversation (same screen as the participants see). */
export default function AdminChats() {
  return <ChatPage adapter={adminChatsAdapter} />;
}
