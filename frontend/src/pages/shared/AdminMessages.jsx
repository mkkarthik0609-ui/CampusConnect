import { useAuth } from "@/auth/AuthProvider";
import { ChatPage } from "@/features/chat/ChatShell";
import { adminMessagesAdapter } from "@/features/chat/adapters";

const ADAPTERS = { ADMIN: adminMessagesAdapter("ADMIN"), FACULTY: adminMessagesAdapter("FACULTY") };

/** Faculty <-> admin messages, WhatsApp style. Admins pick any faculty member; faculty talk to the admin. */
export default function AdminMessages() {
  const { role } = useAuth();
  return <ChatPage adapter={ADAPTERS[role === "ADMIN" ? "ADMIN" : "FACULTY"]} />;
}
