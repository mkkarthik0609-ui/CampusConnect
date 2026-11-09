import { ChatPage } from "./ChatShell";
import { chatAdapter } from "./adapters";

const ADAPTERS = { STUDENT: chatAdapter("STUDENT"), FACULTY: chatAdapter("FACULTY") };

/** Mentor-Connect for students and faculty (`role` = "STUDENT" | "FACULTY"): /student/chat, /faculty/chat. */
export function ChatListView({ role }) {
  return <ChatPage adapter={ADAPTERS[role]} />;
}
