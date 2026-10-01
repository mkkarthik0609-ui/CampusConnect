/**
 * THE route table. Feature agents: to add or replace a page, create/replace the file under
 * src/pages/<role>/ and (only if it is a NEW route) add ONE line to the matching array below.
 * Every page is lazy-loaded: `page(() => import("@/pages/student/Meetings"))`.
 *
 * Guards (see src/auth/guards.jsx):
 *   public            no guard                              /
 *   guest-only        GuestOnly + AuthLayout                /login  /signup/student  /signup/faculty
 *   authenticated     RequireAuth + AppShell                /notifications  /account/password
 *   per role          RequireRole inside the shell          /student/*  /faculty/*  /admin/*
 *
 * Paths below are relative to their role prefix, e.g. { path: "chat/:id" } under STUDENT is /student/chat/:id.
 */
import { Suspense, lazy } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { AppRedirect, GuestOnly, RequireAuth, RequireRole } from "@/auth/guards";
import { AppShell } from "@/components/app/AppShell";
import { AuthLayout } from "@/components/app/AuthLayout";
import { PageLoader } from "@/components/app/PageLoader";
import { RouteAnnouncer } from "@/components/app/RouteAnnouncer";
import { RouteError } from "@/pages/shared/ServerError";
import NotFoundRoute from "@/pages/shared/NotFound";

/** Lazy route element. `page(() => import("@/pages/x/Y"))` -> <Y/> in its own chunk. */
function page(loader) {
  const Component = lazy(loader);
  return <Component />;
}

// ---- student: /student/... ---------------------------------------------------------------
const studentRoutes = [
  { path: "dashboard", element: page(() => import("@/pages/student/Dashboard")) },
  { path: "profile", element: page(() => import("@/pages/student/Profile")) },
  { path: "chat", element: page(() => import("@/pages/student/Chat")) },
  { path: "chat/:id", element: page(() => import("@/pages/student/ChatThread")) },
  { path: "meetings", element: page(() => import("@/pages/student/Meetings")) },
  { path: "meetings/request/:facultyId", element: page(() => import("@/pages/student/RequestMeeting")) },
  { path: "find-faculty", element: page(() => import("@/pages/student/FindFaculty")) },
];

// ---- faculty: /faculty/... ---------------------------------------------------------------
const facultyRoutes = [
  { path: "dashboard", element: page(() => import("@/pages/faculty/Dashboard")) },
  { path: "classes", element: page(() => import("@/pages/faculty/Classes")) },
  { path: "classes/:sectionId", element: page(() => import("@/pages/faculty/ClassDetail")) },
  { path: "profile", element: page(() => import("@/pages/faculty/Profile")) },
  { path: "chat", element: page(() => import("@/pages/faculty/Chat")) },
  { path: "chat/:id", element: page(() => import("@/pages/faculty/ChatThread")) },
  { path: "meetings", element: page(() => import("@/pages/faculty/Meetings")) },
  { path: "find-students", element: page(() => import("@/pages/faculty/FindStudents")) },
  { path: "approvals", element: page(() => import("@/pages/faculty/Approvals")) },
];

// ---- admin: /admin/... -------------------------------------------------------------------
const adminRoutes = [
  { path: "dashboard", element: page(() => import("@/pages/admin/Dashboard")) },
  { path: "academics", element: page(() => import("@/pages/admin/Academics")) },
  { path: "assignments", element: page(() => import("@/pages/admin/Assignments")) },
  { path: "assignment-requests", element: page(() => import("@/pages/admin/AssignmentRequests")) },
  { path: "classes", element: page(() => import("@/pages/admin/Classes")) },
  { path: "classes/:sectionId", element: page(() => import("@/pages/admin/ClassDetail")) },
  { path: "students", element: page(() => import("@/pages/admin/Students")) },
  { path: "faculty", element: page(() => import("@/pages/admin/Faculty")) },
  { path: "meetings", element: page(() => import("@/pages/admin/Meetings")) },
  { path: "chats", element: page(() => import("@/pages/admin/Chats")) },
  { path: "chats/:id", element: page(() => import("@/pages/admin/ChatThread")) },
  { path: "approvals", element: page(() => import("@/pages/admin/Approvals")) },
  { path: "admins", element: page(() => import("@/pages/admin/Admins")) },
  { path: "research", element: page(() => import("@/pages/admin/Research")) },
];

// ---- any signed-in user ------------------------------------------------------------------
const sharedRoutes = [
  { path: "notifications", element: page(() => import("@/pages/shared/Notifications")) },
  { path: "account/password", element: page(() => import("@/pages/shared/ChangePassword")) },
];

/** A role section: exact prefix redirects to its dashboard, everything else needs the role. */
const roleSection = (prefix, role, children) => ({
  path: prefix,
  element: <RequireRole roles={[role]} />,
  children: [{ index: true, element: <Navigate to="dashboard" replace /> }, ...children],
});

function RootLayout() {
  return (
    <>
      <Suspense fallback={<PageLoader />}>
        <Outlet />
      </Suspense>
      <RouteAnnouncer />
    </>
  );
}

export const routes = [
  {
    element: <RootLayout />,
    errorElement: <RouteError />,
    children: [
      // public landing (also reachable when signed in; its header then offers "Open dashboard")
      { path: "/", element: page(() => import("@/pages/site/Landing")) },

      // guest-only: signed-in users are bounced to their home (or ?next=)
      {
        element: <GuestOnly />,
        children: [
          {
            element: <AuthLayout />,
            children: [
              { path: "/login", element: page(() => import("@/pages/site/Login")) },
              { path: "/signup/student", element: page(() => import("@/pages/site/SignupStudent")) },
              { path: "/signup/faculty", element: page(() => import("@/pages/site/SignupFaculty")) },
            ],
          },
        ],
      },

      // "/app" sends each role to its home
      { path: "/app", element: <AppRedirect /> },

      // authenticated shell
      {
        element: <RequireAuth />,
        children: [
          {
            element: <AppShell />,
            children: [
              ...sharedRoutes,
              roleSection("student", "STUDENT", studentRoutes),
              roleSection("faculty", "FACULTY", facultyRoutes),
              roleSection("admin", "ADMIN", adminRoutes),
            ],
          },
        ],
      },

      { path: "*", element: <NotFoundRoute /> },
    ],
  },
];
