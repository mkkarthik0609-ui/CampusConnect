import { Construction } from "lucide-react";
import { PageHeader } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { useLocation } from "react-router-dom";

/**
 * Stand-in for a page a feature agent has not built yet.
 * Replace the page file's default export with the real page; keep the same file path (routes.jsx imports it).
 *
 *   export default function Meetings() {
 *     return <PagePlaceholder title="Meetings" file="pages/student/Meetings.jsx" endpoints={["GET /api/meetings"]} />;
 *   }
 */
export function PagePlaceholder({ title, description, file, endpoints = [] }) {
  const { pathname } = useLocation();
  return (
    <>
      <PageHeader title={title} description={description} />
      <div className="rounded-lg border bg-card shadow-sm">
        <EmptyState icon={Construction} title="This page is not built yet">
          <p>
            Route <code className="rounded bg-sunken px-1.5 py-0.5 font-mono text-[0.8125rem] text-ink-2">{pathname}</code> is wired up and
            guarded. The screen itself is still to come{file ? <> in <code className="rounded bg-sunken px-1.5 py-0.5 font-mono text-[0.8125rem] text-ink-2">src/{file}</code></> : null}.
          </p>
          {endpoints.length ? (
            <ul className="m-0 grid list-none gap-1 p-0 text-left font-mono text-[0.8125rem] text-ink-2">
              {endpoints.map((e) => <li key={e}>{e}</li>)}
            </ul>
          ) : null}
        </EmptyState>
      </div>
    </>
  );
}
