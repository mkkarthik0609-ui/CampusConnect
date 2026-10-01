/**
 * Sidebar navigation per role. The AppShell renders this; feature agents only edit it when they add a page
 * that needs a sidebar entry. `badge` picks an unread counter from useAuth().unread.
 * `icon` is a lucide-react component.
 */
import {
  Bell, BookOpen, CalendarDays, CircleCheck, FlaskConical, Inbox, LayoutDashboard, LayoutGrid, Layers, Link2,
  MessagesSquare, Search, ShieldCheck, UserRound, Users,
} from "lucide-react";

const notifications = { to: "/notifications", label: "Notifications", icon: Bell, badge: "notifications" };

export const NAV = {
  STUDENT: [
    { items: [{ to: "/student/dashboard", label: "Dashboard", icon: LayoutDashboard }] },
    {
      label: "Mentoring",
      items: [
        { to: "/student/chat", label: "Mentor-Connect", icon: MessagesSquare, badge: "messages" },
        { to: "/student/meetings", label: "Meetings", icon: CalendarDays },
        { to: "/student/find-faculty", label: "Find Faculty", icon: Search },
      ],
    },
    {
      label: "You",
      items: [{ to: "/student/profile", label: "Profile", icon: UserRound }, notifications],
    },
  ],
  FACULTY: [
    { items: [{ to: "/faculty/dashboard", label: "Dashboard", icon: LayoutDashboard }] },
    {
      label: "Classes",
      items: [
        { to: "/faculty/classes", label: "My Classes", icon: Layers },
        { to: "/faculty/find-students", label: "Find Student", icon: Search },
      ],
    },
    {
      label: "Mentoring",
      items: [
        { to: "/faculty/chat", label: "Mentor-Connect", icon: MessagesSquare, badge: "messages" },
        { to: "/faculty/meetings", label: "Meetings", icon: CalendarDays },
        { to: "/faculty/approvals", label: "Approvals", icon: CircleCheck },
      ],
    },
    {
      label: "You",
      items: [{ to: "/faculty/profile", label: "Profile", icon: UserRound }, notifications],
    },
  ],
  ADMIN: [
    { items: [{ to: "/admin/dashboard", label: "Dashboard", icon: LayoutDashboard }] },
    {
      label: "Academics",
      items: [
        { to: "/admin/academics", label: "Academics", icon: Layers },
        { to: "/admin/classes", label: "Classes", icon: LayoutGrid },
        { to: "/admin/assignments", label: "Assignments", icon: Link2 },
        { to: "/admin/assignment-requests", label: "Class requests", icon: Inbox },
      ],
    },
    {
      label: "People",
      items: [
        { to: "/admin/students", label: "Students", icon: Users },
        { to: "/admin/faculty", label: "Faculty", icon: BookOpen },
        { to: "/admin/admins", label: "Admins", icon: ShieldCheck },
      ],
    },
    {
      label: "Oversight",
      items: [
        { to: "/admin/meetings", label: "Meetings", icon: CalendarDays },
        { to: "/admin/chats", label: "Chats", icon: MessagesSquare },
        { to: "/admin/approvals", label: "Approvals", icon: CircleCheck },
        { to: "/admin/research", label: "Research", icon: FlaskConical },
        notifications,
      ],
    },
  ],
};

/** Where `/app` (and a signed-in visit to /login) sends each role. */
export const ROLE_HOME = {
  STUDENT: "/student/dashboard",
  FACULTY: "/faculty/dashboard",
  ADMIN: "/admin/dashboard",
};

export const ROLE_LABEL = { STUDENT: "Student", FACULTY: "Faculty", ADMIN: "Admin" };

export function homeFor(role) {
  return ROLE_HOME[role] || "/login";
}
