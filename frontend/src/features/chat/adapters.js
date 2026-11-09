/**
 * One adapter per messaging surface. The shared UI (ChatShell / ChatList / ThreadPane) only talks to this shape:
 *
 *   key, listKey, threadKey(id)   react-query keys
 *   basePath, selectBy            where a conversation lives: "param" => `${basePath}/:id`, "query" => `${basePath}?c=:id`
 *   title, readOnly, canAttach, showSenderNames, autoOpenSingle, newChat, emptyText
 *   fetchList()    -> rows  [{ id, name, src, avatars?, subtitle?, preview, unsent, attachment, mine, status, time, unread, typing, online }]
 *   fetchThread(id, { afterId, since }) -> { other: { id, name, src, avatars?, subtitle, online, lastActiveAt, typing }, messages, lastId, serverTime }
 *   send / edit / unsend / hide / typing   (not used when readOnly)
 *   headerLink(other) -> { to, label } | null
 */
import { adminApi, adminKeys, adminMessagesApi, chatApi } from "@/lib/endpoints";
import { queryKeys } from "@/lib/queryClient";

const IMAGE_TYPES = ["png", "jpg", "jpeg"];

function chatRows(data) {
  return (data?.items || []).map((c) => ({
    id: c.chat_id,
    name: c.other.full_name,
    src: c.other.profile_picture_url,
    preview: c.last_message,
    unsent: !!c.last_message_is_unsent,
    attachment: !!c.last_message?.startsWith("Attachment:"),
    mine: !!c.last_message_is_mine,
    status: c.last_message_status,
    time: c.last_message_at,
    unread: c.unread_count,
    typing: !!c.other.typing,
    online: !!c.other.online,
  }));
}

const describe = (o) => (o.role === "STUDENT" ? o.usn : [o.faculty_code, o.department].filter(Boolean).join(" - "));

function otherParty(o) {
  return {
    id: o.id, name: o.full_name, src: o.profile_picture_url, subtitle: describe(o),
    online: !!o.online, lastActiveAt: o.last_active_at, typing: !!o.typing,
  };
}

function threadResult(data) {
  return { other: otherParty(data.chat.other), messages: data.messages, lastId: data.last_id, serverTime: data.server_time };
}

/** Student <-> faculty chats (`role` = "STUDENT" | "FACULTY"). */
export function chatAdapter(role) {
  const student = role === "STUDENT";
  return {
    key: "chat",
    listKey: queryKeys.chats,
    threadKey: (id) => queryKeys.chat(id),
    basePath: student ? "/student/chat" : "/faculty/chat",
    selectBy: "param",
    title: "Mentor-Connect",
    readOnly: false,
    canAttach: true,
    newChat: { to: student ? "/student/find-faculty" : "/faculty/find-students", label: student ? "Find faculty" : "Find a student" },
    emptyText: student
      ? "No conversations yet. Message the faculty assigned to your class, or find a faculty member who can support you."
      : "No conversations yet. Open a student from one of your classes, or search for a student.",
    fetchList: async () => chatRows(await chatApi.list()),
    fetchThread: async (id, opts) => threadResult(await chatApi.get(id, opts)),
    send: (id, body) => chatApi.send(id, body),
    edit: (mid, text) => chatApi.edit(mid, text),
    unsend: (mid) => chatApi.unsend(mid),
    hide: (mid) => chatApi.hide(mid),
    typing: (id) => chatApi.typing(id),
    headerLink: (other) => (student && other?.id ? { to: `/student/meetings/request/${other.id}`, label: "Request a meeting" } : null),
  };
}

/** Faculty <-> admin messages. Admins see every faculty member; faculty see their one conversation with the admin. */
export function adminMessagesAdapter(role) {
  const admin = role === "ADMIN";
  const key = ["admin-messages", "list"];
  return {
    key: "admin-messages",
    listKey: key,
    threadKey: (id) => ["admin-messages", "thread", String(id)],
    basePath: admin ? "/admin/faculty-messages" : "/faculty/admin-messages",
    selectBy: "query",
    title: admin ? "Faculty messages" : "Message Admin",
    readOnly: false,
    canAttach: false,
    autoOpenSingle: !admin,
    emptyText: admin ? "No faculty members yet." : "The admin is not available yet.",
    fetchList: async () =>
      (await adminMessagesApi.list()).items.map((c) => ({
        id: c.conversation_id,
        name: c.other.full_name,
        src: c.other.profile_picture_url,
        subtitle: c.other.faculty_code || undefined,
        preview: c.last_message,
        unsent: !!c.last_message_is_unsent,
        mine: !!c.last_message_is_mine,
        status: c.last_message_status,
        time: c.last_message_at,
        unread: c.unread_count,
        typing: !!c.other.typing,
        online: !!c.other.online,
      })),
    fetchThread: async (id, opts) => {
      const data = await adminMessagesApi.thread(id, opts);
      const o = data.chat.other;
      return {
        other: {
          id: o.id, name: o.full_name, src: o.profile_picture_url,
          subtitle: o.role === "FACULTY" ? [o.faculty_code, o.department].filter(Boolean).join(" - ") : "Campus Admin",
          online: !!o.online, lastActiveAt: o.last_active_at, typing: !!o.typing,
        },
        messages: data.messages, lastId: data.last_id, serverTime: data.server_time,
      };
    },
    send: (id, { text, replyToId }) =>
      adminMessagesApi.send({ message_text: text, ...(admin ? { recipient_user_id: Number(id) } : {}), ...(replyToId ? { reply_to_id: replyToId } : {}) }),
    edit: (mid, text) => adminMessagesApi.edit(mid, text),
    unsend: (mid) => adminMessagesApi.unsend(mid),
    hide: (mid) => adminMessagesApi.hide(mid),
    typing: (id) => adminMessagesApi.typing(id),
    headerLink: () => null,
  };
}

/** Admin read-only viewer of every student <-> faculty conversation. */
export const adminChatsAdapter = {
  key: "admin-chat",
  listKey: adminKeys.chats,
  threadKey: (id) => adminKeys.chat(id),
  basePath: "/admin/chats",
  selectBy: "param",
  title: "Chats",
  readOnly: true,
  canAttach: false,
  showSenderNames: true,
  emptyText: "No conversations yet. Chats start when a student or faculty member sends a first message.",
  fetchList: async () =>
    (await adminApi.chats()).items.map((c) => ({
      id: c.id,
      name: `${c.student.full_name} and ${c.faculty.full_name}`,
      avatars: [{ name: c.student.full_name, src: c.student.profile_picture_url }, { name: c.faculty.full_name, src: c.faculty.profile_picture_url }],
      subtitle: `${c.student.usn} / ${c.faculty.faculty_code}`,
      preview: c.last_message,
      unsent: /unsent a message$/.test(c.last_message || ""),
      time: c.last_message_at || c.updated_at,
      unread: 0,
    })),
  fetchThread: async (id, opts) => {
    const data = await adminApi.chat(id, opts);
    const { student, faculty } = data.chat;
    const messages = data.messages.map((m) => ({
      id: m.id,
      is_mine: m.sender_role === "FACULTY",
      sender_name: m.sender_name,
      message_text: m.message_text,
      attachment: m.attachment_url
        ? { url: m.attachment_url, name: m.attachment_name, type: m.attachment_type, is_image: IMAGE_TYPES.includes((m.attachment_type || "").toLowerCase()) }
        : null,
      status: m.status,
      is_edited: m.is_edited,
      is_unsent: m.is_unsent,
      can_edit: false,
      can_unsend: false,
      reply_to: m.reply_to && { ...m.reply_to, is_mine: m.reply_to.sender_user_id === faculty.user_id },
      created_at: m.created_at,
    }));
    return {
      other: {
        id: data.chat.id, name: `${student.full_name} and ${faculty.full_name}`,
        avatars: [{ name: student.full_name, src: student.profile_picture_url }, { name: faculty.full_name, src: faculty.profile_picture_url }],
        subtitle: `Student ${student.usn}, faculty ${faculty.faculty_code} - ${data.chat.message_count} ${data.chat.message_count === 1 ? "message" : "messages"}`,
        online: false, typing: false,
      },
      messages, lastId: data.last_id, serverTime: data.server_time,
    };
  },
  headerLink: () => null,
};
