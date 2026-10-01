import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/app/PageHeader";
import { EmptyState } from "@/components/app/EmptyState";
import { ListSkeleton } from "@/components/app/PageLoader";
import { Notice } from "@/components/app/Notice";
import { ConfirmDialog, PromptDialog } from "@/components/app/dialogs";
import { meetingsApi } from "@/lib/endpoints";
import { queryKeys } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import { MeetingCard } from "./MeetingCard";
import { RespondDialog } from "./RespondDialog";
import { MEETING_TABS, useMeetingActions } from "./useMeetingActions";

/** Meetings list for both roles (`role` = "STUDENT" | "FACULTY"): status tabs, respond / cancel / complete. */
export function MeetingsView({ role }) {
  const faculty = role === "FACULTY";
  const [params, setParams] = useSearchParams();
  const tab = MEETING_TABS.some((t) => t.value === params.get("status")) ? params.get("status") : "all";
  const { respond, cancel, complete } = useMeetingActions();
  const [respondTarget, setRespondTarget] = useState(null);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [completeTarget, setCompleteTarget] = useState(null);

  const query = useQuery({ queryKey: queryKeys.meetings, queryFn: () => meetingsApi.list(), refetchInterval: 30_000 });
  const all = useMemo(() => query.data?.items || [], [query.data]);

  const counts = useMemo(() => {
    const c = { all: all.length };
    for (const m of all) c[m.status.toLowerCase()] = (c[m.status.toLowerCase()] || 0) + 1;
    return c;
  }, [all]);
  const shown = tab === "all" ? all : all.filter((m) => m.status.toLowerCase() === tab);

  const setTab = (value) => setParams(value === "all" ? {} : { status: value }, { replace: true });
  const tabLabel = MEETING_TABS.find((t) => t.value === tab)?.label.toLowerCase();

  return (
    <>
      <PageHeader
        title={faculty ? "Meeting requests" : "My meetings"}
        description={
          faculty
            ? "Accept a request and give a time in your own words; there are no fixed slots."
            : "Faculty reply with a time in their own words. Mark a meeting completed once it has happened."
        }
        actions={
          !faculty ? (
            <Button asChild variant="outline"><Link to="/student/find-faculty"><Search aria-hidden="true" /> Find faculty</Link></Button>
          ) : null
        }
      />

      <Tabs value={tab} onValueChange={setTab} className="gap-3">
        <div className="-mx-1 overflow-x-auto px-1 pb-1 no-scrollbar">
          <TabsList aria-label="Filter meetings by status" className="min-w-max">
            {MEETING_TABS.map((t) => {
              const n = counts[t.value] || 0;
              return (
                <TabsTrigger key={t.value} value={t.value}>
                  {t.label}
                  {query.data ? (
                    <span
                      className={cn(
                        "ml-0.5 rounded-full px-1.5 text-xs font-bold tabular-nums",
                        t.value === "pending" && n > 0 ? "bg-saffron text-on-saffron" : "bg-sunken text-muted-foreground",
                      )}
                    >
                      {n}
                      <span className="sr-only"> {n === 1 ? "meeting" : "meetings"}</span>
                    </span>
                  ) : null}
                </TabsTrigger>
              );
            })}
          </TabsList>
        </div>

        <TabsContent value={tab} className="overflow-hidden rounded-lg border border-line bg-card shadow-sm">
          {query.isPending ? (
            <ListSkeleton rows={3} className="p-3" />
          ) : query.isError ? (
            <div className="p-3">
              <Notice tone="danger" title="Could not load your meetings">
                {query.error.message}
                <Button variant="outline" size="sm" className="mt-2" onClick={() => query.refetch()}>Try again</Button>
              </Notice>
            </div>
          ) : shown.length === 0 ? (
            tab === "all" ? (
              <EmptyState icon={CalendarDays} title={faculty ? "No meeting requests yet" : "No meetings yet"}>
                {faculty ? (
                  <p>When a student asks to meet you, the request lands here and you reply with a time.</p>
                ) : (
                  <p>Request a meeting from a faculty member on your dashboard, or find one who can support you.</p>
                )}
                {!faculty ? (
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button asChild><Link to="/student/dashboard">Go to dashboard</Link></Button>
                    <Button asChild variant="outline"><Link to="/student/find-faculty">Find faculty</Link></Button>
                  </div>
                ) : null}
              </EmptyState>
            ) : (
              <EmptyState icon={CalendarDays} compact className="px-5" title={`Nothing ${tabLabel}`}>
                <p>No {tabLabel} meetings right now.</p>
                <Button variant="link" className="mt-1" onClick={() => setTab("all")}>Show all meetings</Button>
              </EmptyState>
            )
          ) : (
            <div>
              {shown.map((m) => (
                <MeetingCard key={m.id} meeting={m} role={role} onRespond={setRespondTarget} onCancel={setCancelTarget} onComplete={setCompleteTarget} />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      <RespondDialog
        meeting={respondTarget}
        open={!!respondTarget}
        onOpenChange={(o) => { if (!o) setRespondTarget(null); }}
        onRespond={(body) => respond.mutateAsync({ id: respondTarget.id, ...body })}
      />

      <PromptDialog
        open={!!cancelTarget}
        onOpenChange={(o) => { if (!o) setCancelTarget(null); }}
        title="Cancel this meeting?"
        description={cancelTarget ? `${cancelTarget.counterpart_name} will be told. This cannot be undone.` : undefined}
        label="Reason for cancelling"
        required={!faculty}
        placeholder={faculty ? "Optional" : "For example: I have a lab session at that time"}
        confirmLabel="Cancel meeting"
        cancelLabel="Keep meeting"
        destructive
        onSubmit={(reason) => cancel.mutateAsync({ id: cancelTarget.id, reason })}
      />

      <ConfirmDialog
        open={!!completeTarget}
        onOpenChange={(o) => { if (!o) setCompleteTarget(null); }}
        title="Mark this meeting as completed?"
        description={completeTarget ? `Confirm that your meeting with ${completeTarget.counterpart_name} has taken place.` : undefined}
        confirmLabel="Mark completed"
        onConfirm={() => complete.mutateAsync(completeTarget.id)}
      />
    </>
  );
}
