import { Check, ChevronRight, Paperclip } from "lucide-react";
import { StatusPill } from "@/components/app/StatusPill";
import { cn } from "@/lib/utils";

/** Compact product mocks for the showcase (text from the original landing scenes). Card tokens, so they follow the theme. */

const shell = "w-full max-w-[34rem] overflow-hidden rounded-2xl border bg-card text-card-foreground shadow-md";

const LEVELS = [
  { label: "Branch", items: ["CSE", "ECE"], pick: 0 },
  { label: "Department", items: ["AIML", "Cyber Security"], pick: 0 },
  { label: "Year", items: ["2nd Year", "3rd Year"], pick: 1 },
  { label: "Section", items: ["A", "B"], pick: 0 },
];

export function ClassMock() {
  return (
    <div className={cn(shell, "p-4")}>
      <div className="grid gap-3">
        {LEVELS.map((lv) => (
          <div key={lv.label} className="grid grid-cols-[5.5rem_1fr] items-center gap-3">
            <span className="text-[0.8125rem] font-semibold text-muted-foreground">{lv.label}</span>
            <div className="flex flex-wrap gap-1.5">
              {lv.items.map((it, i) => (
                <span key={it} className={cn("rounded-full px-3 py-1 text-[0.875rem] font-semibold", i === lv.pick ? "bg-primary text-primary-foreground" : "bg-sunken text-ink-2")}>{it}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-4 mb-0 flex flex-wrap items-center gap-x-1 gap-y-1 border-t pt-3 text-[0.9375rem] font-semibold">
        CSE <ChevronRight aria-hidden="true" className="size-4 text-muted-foreground" />
        AIML <ChevronRight aria-hidden="true" className="size-4 text-muted-foreground" />
        3rd Year <ChevronRight aria-hidden="true" className="size-4 text-muted-foreground" />
        A
        <span className="ml-auto font-mono text-[0.8125rem] font-normal text-muted-foreground">stored as one section_id</span>
      </p>
    </div>
  );
}

export function ChatMock() {
  return (
    <div className={shell}>
      <p className="m-0 flex flex-wrap items-center gap-x-1.5 border-b px-4 py-3 text-[0.8125rem] font-semibold">
        <Check aria-hidden="true" className="size-4" /> Same class chain
        <span className="font-normal text-muted-foreground">CSE, AIML, 3rd Year, A</span>
      </p>
      <div className="flex flex-col gap-2 bg-surface-2 p-4">
        <div className="bubble bubble-mine">Sir, my report is ready. Can I show it before Friday?</div>
        <div className="flex items-center gap-1.5 self-end rounded-md border bg-card px-2.5 py-1 text-[0.8125rem] font-semibold text-ink-2">
          <Paperclip aria-hidden="true" className="size-3.5" /> project-report.pdf
        </div>
        <div className="bubble bubble-theirs">Received. Request a slot and I will set the time.</div>
      </div>
      <p className="m-0 flex items-center justify-between gap-3 border-t px-4 py-2.5 text-[0.8125rem] text-muted-foreground">
        <span className="font-semibold text-ink-2">Edit allowed</span>
        <span>PDF, image or DOCX</span>
      </p>
    </div>
  );
}

const STEPS = ["Pending", "Accepted", "Completed"];

export function MeetingMock() {
  return (
    <div className={cn(shell, "p-4")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="m-0 text-[0.9375rem] font-semibold">Project report review</p>
          <p className="m-0 text-[0.8125rem] text-muted-foreground">Ananya R. with Dr. Meera Iyer</p>
        </div>
        <StatusPill status="ACCEPTED" />
      </div>
      <p className="mt-3 mb-0 border-t pt-3 text-[0.9375rem]">
        <span className="font-semibold">Reply from Dr. Iyer:</span> Thursday, 11:30. Bring the printed copy.
      </p>
      <div className="mt-4">
        <div className="mb-2 h-1 rounded-full bg-sunken"><div className="h-full w-1/2 rounded-full bg-primary" /></div>
        <ol className="m-0 grid list-none grid-cols-3 p-0 text-[0.8125rem] font-semibold">
          {STEPS.map((s, i) => (
            <li key={s} className={cn(i === 1 && "text-center", i === 2 && "text-right text-muted-foreground")}>{s}</li>
          ))}
        </ol>
      </div>
      <p className="mt-4 mb-0 text-[0.8125rem] text-muted-foreground">Either side can cancel at any point, but a reason is required.</p>
    </div>
  );
}
