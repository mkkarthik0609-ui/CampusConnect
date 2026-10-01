/**
 * Where a notification should take the reader. Best-effort mapping from the notification_type values in
 * services/notification_service.py to SPA routes. Returns null when there is nothing to open.
 */
export function notificationTarget(n, role) {
  const prefix = { STUDENT: "/student", FACULTY: "/faculty", ADMIN: "/admin" }[role];
  if (!prefix || !n) return null;
  const type = String(n.type || n.notification_type || "");

  if (type.startsWith("MEETING_")) return `${prefix}/meetings`;
  if (type === "NEW_MESSAGE") {
    const ent = String(n.related_entity_type || "").toLowerCase();
    const isChat = ent.includes("chat") || ent.includes("conversation") || ent.includes("thread");
    return n.related_entity_id && isChat ? `${prefix}/chat/${n.related_entity_id}` : `${prefix}/chat`;
  }
  if (type.startsWith("SUPPORTING_")) return role === "STUDENT" ? "/student/find-faculty" : role === "FACULTY" ? "/faculty/find-students" : null;
  if (type === "PERMISSION_REQUESTED") return role === "ADMIN" ? "/admin/approvals" : null;
  if (type === "PERMISSION_RESPONDED") return role === "ADMIN" ? "/admin/approvals" : `${prefix}/profile`;
  if (type === "ASSIGNMENT_REQUESTED") return role === "ADMIN" ? "/admin/assignment-requests" : null;
  if (type.startsWith("ASSIGNMENT_")) return role === "FACULTY" ? "/faculty/classes" : null;
  return null;
}
