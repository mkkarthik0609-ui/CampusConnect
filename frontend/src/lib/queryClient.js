import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";

/** One QueryClient for the app. Keep keys in `queryKeys` so invalidation stays greppable. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry(failureCount, error) {
        // never retry client errors; GET network errors / 502-504 are already retried with backoff in lib/api.js
        if (error instanceof ApiError && (error.status < 500 || [502, 503, 504].includes(error.status))) return false;
        return failureCount < 1;
      },
    },
    mutations: { retry: false },
  },
});

export const queryKeys = {
  session: ["session"],
  academicTree: ["academic", "tree"],
  notifications: ["notifications"],
  // student / chat / meetings / supporting (feature keys)
  studentDashboard: ["student", "dashboard"],
  studentProfile: ["student", "profile"],
  chats: ["chats"],
  chat: (id) => ["chat", String(id)],
  meetings: ["meetings"],
  supporting: ["supporting"],
  facultySearch: (q) => ["supporting", "faculty-search", q],
  // Feature agents: add keys here, e.g. thing: (filters) => ["thing", filters]
};
