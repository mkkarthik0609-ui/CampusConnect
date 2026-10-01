import { useId, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronRight, EyeOff, MoreHorizontal, Plus, Trash2, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SubmitButton } from "@/components/app/SubmitButton";
import { ConfirmDialog, useConfirm } from "@/components/app/dialogs";
import { StatusPill } from "@/components/app/StatusPill";
import { ApiError, errorMessage } from "@/lib/api";
import { adminApi, adminKeys } from "@/lib/endpoints";
import { queryKeys } from "@/lib/queryClient";
import { pluralize } from "@/lib/format";
import { cn } from "@/lib/utils";

const LEVEL_LABEL = { branch: "branch", department: "department", year: "year", section: "section" };

const ADD = {
  branch: { label: "Add department", field: "Department name", placeholder: "e.g. AIML", call: (id, v) => adminApi.addDepartment(id, v), errKey: "name" },
  department: { label: "Add year", field: "Year", placeholder: "e.g. 3 or 3rd Year", call: (id, v) => adminApi.addYear(id, v), errKey: "name" },
  year: { label: "Add sections", field: "Section letters", placeholder: "A, B, C", call: (id, v) => adminApi.addSections(id, v), errKey: "names" },
};

function counts(node) {
  return `${pluralize(node.student_count, "student")} · ${pluralize(node.assignment_count, "assignment")}`;
}

/** One-line add form: used for branches, departments, years and sections. */
export function AddInline({ label, field, placeholder, onSubmit, onCancel, errKey = "name", autoFocus = true }) {
  const id = useId();
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (!value.trim()) {
      setError(`${field} is required.`);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSubmit(value.trim());
      setValue("");
      onCancel?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.fields?.[errKey] || err.fields?.name || err.fields?.names || err.message : errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="grid gap-1.5">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[10rem] flex-1">
          <label htmlFor={id} className="mb-1 block text-[0.8125rem] font-semibold text-ink-2">{field}</label>
          <Input
            id={id}
            value={value}
            autoFocus={autoFocus}
            placeholder={placeholder}
            maxLength={60}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? `${id}-err` : undefined}
            onChange={(e) => { setValue(e.target.value); if (error) setError(""); }}
            onKeyDown={(e) => { if (e.key === "Escape" && onCancel) onCancel(); }}
            className="h-10"
          />
        </div>
        <SubmitButton loading={busy} size="sm" className="min-h-10">{label}</SubmitButton>
        {onCancel ? <Button type="button" variant="ghost" size="sm" className="min-h-10" onClick={onCancel}>Cancel</Button> : null}
      </div>
      {error ? <p id={`${id}-err`} role="alert" className="text-[0.8125rem] font-semibold text-danger-ink">{error}</p> : null}
    </form>
  );
}

function NodeMenu({ level, node, onToggleActive, onDelete }) {
  const name = `${LEVEL_LABEL[level]} ${node.name}`;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="ghost" size="icon-sm" aria-label={`Actions for ${name}`}>
          <MoreHorizontal aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel className="font-semibold">{name}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => onToggleActive(level, node)}>
          {node.is_active ? <EyeOff aria-hidden="true" /> : <Undo2 aria-hidden="true" />}
          {node.is_active ? "Deactivate" : "Reactivate"}
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" disabled={!node.can_delete} onSelect={() => onDelete(level, node)}>
          <Trash2 aria-hidden="true" />
          {node.can_delete ? "Delete" : "Delete (in use, deactivate instead)"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SectionChip({ node, onToggleActive, onDelete }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`Section ${node.name}, ${node.is_active ? "active" : "inactive"}, ${counts(node)}. Open actions`}
          className={cn(
            "inline-flex min-h-8 min-w-10 items-center justify-center gap-1.5 rounded-full border px-3 text-sm font-bold transition-colors pointer-coarse:min-h-11",
            node.is_active
              ? "border-primary/30 bg-primary-soft text-primary-ink hover:border-primary"
              : "border-dashed border-line-strong bg-transparent text-muted-foreground line-through hover:border-muted-foreground",
          )}
        >
          {node.name}
          {!node.is_active ? <span className="text-[0.7rem] font-semibold tracking-wide uppercase no-underline [text-decoration:none]">off</span> : null}
          {node.student_count ? <span className="num rounded-full bg-card/70 px-1.5 text-[0.7rem] font-semibold [text-decoration:none]">{node.student_count}</span> : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-56">
        <DropdownMenuLabel className="font-semibold">Section {node.name} <span className="font-normal text-muted-foreground">({counts(node)})</span></DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => onToggleActive("section", node)}>
          {node.is_active ? <EyeOff aria-hidden="true" /> : <Undo2 aria-hidden="true" />}
          {node.is_active ? "Deactivate" : "Reactivate"}
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" disabled={!node.can_delete} onSelect={() => onDelete("section", node)}>
          <Trash2 aria-hidden="true" />
          {node.can_delete ? "Delete" : "Delete (in use, deactivate instead)"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Row({ level, node, open, onToggle, adding, onAdd, actions, extra, parentInactive }) {
  const hasChildren = level !== "year";
  const childCount = level === "branch" ? node.departments.length : level === "department" ? node.years.length : node.sections.length;
  const childNoun = level === "branch" ? "department" : level === "department" ? "year" : "section";
  const headingId = useId();
  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 py-2">
        {hasChildren ? (
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            aria-controls={`${headingId}-body`}
            className="group -ml-1.5 inline-flex min-h-9 min-w-0 items-center gap-1.5 rounded-md px-1.5 text-left hover:bg-primary-soft pointer-coarse:min-h-11"
          >
            <ChevronRight aria-hidden="true" className={cn("size-4 shrink-0 text-muted-foreground transition-transform motion-reduce:transition-none", open && "rotate-90")} />
            <span className={cn("truncate", level === "branch" ? "font-display text-lg font-bold" : "font-semibold", !node.is_active && "text-muted-foreground")}>{node.name}</span>
            <span className="text-[0.8125rem] font-normal text-muted-foreground">{pluralize(childCount, childNoun)}</span>
          </button>
        ) : (
          <span className={cn("font-semibold", !node.is_active && "text-muted-foreground")}>{node.name}</span>
        )}
        {!node.is_active ? <StatusPill status="INACTIVE" label="Inactive" /> : parentInactive ? <StatusPill status="INACTIVE" label="Hidden by parent" /> : null}
        <span className="num text-[0.8125rem] text-muted-foreground">{counts(node)}</span>
        <div className="ml-auto flex items-center gap-1">
          <Button type="button" variant="outline" size="sm" onClick={onAdd} aria-expanded={adding}>
            <Plus aria-hidden="true" />
            {ADD[level].label}
          </Button>
          {actions}
        </div>
      </div>
      {adding ? <div className="mb-2 rounded-md border border-dashed border-line-strong bg-surface-2 p-3">{adding}</div> : null}
      <div id={`${headingId}-body`}>{extra}</div>
    </div>
  );
}

export function AcademicTree({ branches }) {
  const qc = useQueryClient();
  const confirm = useConfirm();
  const [open, setOpen] = useState(() => new Set(branches.map((b) => `branch-${b.id}`)));
  const [addingKey, setAddingKey] = useState(null);
  const [deleting, setDeleting] = useState(null); // { level, node }

  const refresh = () => Promise.all([
    qc.invalidateQueries({ queryKey: adminKeys.academics }),
    qc.invalidateQueries({ queryKey: queryKeys.academicTree }),
    qc.invalidateQueries({ queryKey: adminKeys.dashboard }),
    qc.invalidateQueries({ queryKey: adminKeys.classes }),
  ]);

  const activeMut = useMutation({
    mutationFn: ({ level, id, active }) => adminApi.setActive(level, id, active),
    onSuccess: (res) => { toast.success(res.message); return refresh(); },
    onError: (err) => toast.error(errorMessage(err)),
  });

  const keyOf = (level, node) => `${level}-${node.id}`;
  const toggle = (k) => setOpen((prev) => { const n = new Set(prev); if (n.has(k)) n.delete(k); else n.add(k); return n; });

  async function toggleActive(level, node) {
    if (node.is_active) {
      const ok = await confirm({
        title: `Deactivate ${LEVEL_LABEL[level]} ${node.name}?`,
        description: `It${level === "section" ? "" : " and everything below it"} will be hidden from registration, class requests and assignments. Nothing is deleted, and you can reactivate it later.`,
        confirmLabel: "Deactivate",
        destructive: true,
      });
      if (!ok) return;
    }
    activeMut.mutate({ level, id: node.id, active: !node.is_active });
  }

  const addTo = (level, node) => (value) => ADD[level].call(node.id, value).then(async (res) => { toast.success(res.message); await refresh(); if (level !== "year") setOpen((p) => new Set(p).add(keyOf(level, node))); });

  const addForm = (level, node) => addingKey === keyOf(level, node)
    ? <AddInline label={ADD[level].label} field={ADD[level].field} placeholder={ADD[level].placeholder} errKey={ADD[level].errKey} onSubmit={addTo(level, node)} onCancel={() => setAddingKey(null)} />
    : null;

  const menu = (level, node) => <NodeMenu level={level} node={node} onToggleActive={toggleActive} onDelete={(l, n) => setDeleting({ level: l, node: n })} />;
  const startAdd = (level, node) => () => setAddingKey((k) => (k === keyOf(level, node) ? null : keyOf(level, node)));

  const allKeys = branches.flatMap((b) => [keyOf("branch", b), ...b.departments.flatMap((d) => [keyOf("department", d)])]);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(new Set(allKeys))}>Expand all</Button>
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(new Set())}>Collapse all</Button>
      </div>

      <ul className="m-0 grid list-none gap-4 p-0">
        {branches.map((b) => (
          <li key={b.id} className="rounded-lg border bg-card px-4 py-1 shadow-sm">
            <Row
              level="branch" node={b} open={open.has(keyOf("branch", b))} onToggle={() => toggle(keyOf("branch", b))}
              adding={addForm("branch", b)} onAdd={startAdd("branch", b)} actions={menu("branch", b)}
              extra={open.has(keyOf("branch", b)) ? (
                b.departments.length ? (
                  <ul className="m-0 mb-2 ml-3 list-none border-l-2 border-line pl-4">
                    {b.departments.map((d) => (
                      <li key={d.id} className="border-b border-line last:border-b-0">
                        <Row
                          level="department" node={d} parentInactive={!b.is_active && d.is_active}
                          open={open.has(keyOf("department", d))} onToggle={() => toggle(keyOf("department", d))}
                          adding={addForm("department", d)} onAdd={startAdd("department", d)} actions={menu("department", d)}
                          extra={open.has(keyOf("department", d)) ? (
                            d.years.length ? (
                              <ul className="m-0 mb-2 ml-3 list-none border-l-2 border-line pl-4">
                                {d.years.map((y) => (
                                  <li key={y.id} className="border-b border-dashed border-line last:border-b-0">
                                    <Row
                                      level="year" node={y} parentInactive={(!b.is_active || !d.is_active) && y.is_active}
                                      adding={addForm("year", y)} onAdd={startAdd("year", y)} actions={menu("year", y)}
                                      extra={
                                        <div className="mb-2.5 flex flex-wrap items-center gap-1.5" role="group" aria-label={`Sections of ${d.name} ${y.name}`}>
                                          {y.sections.length ? y.sections.map((s) => (
                                            <SectionChip key={s.id} node={s} onToggleActive={toggleActive} onDelete={(l, n) => setDeleting({ level: l, node: n })} />
                                          )) : <span className="text-sm text-muted-foreground">No sections yet.</span>}
                                        </div>
                                      }
                                    />
                                  </li>
                                ))}
                              </ul>
                            ) : <p className="mb-3 ml-3 pl-4 text-sm text-muted-foreground">No years yet. Add 1st Year to start.</p>
                          ) : null}
                        />
                      </li>
                    ))}
                  </ul>
                ) : <p className="mb-3 ml-3 pl-4 text-sm text-muted-foreground">No departments yet.</p>
              ) : null}
            />
          </li>
        ))}
      </ul>

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => { if (!o) setDeleting(null); }}
        title={deleting ? `Delete ${LEVEL_LABEL[deleting.level]} ${deleting.node.name}?` : "Delete"}
        description={deleting?.level === "section" ? "This section is empty and will be removed permanently." : "It is unused. It and everything below it will be removed permanently."}
        confirmLabel="Delete"
        destructive
        onConfirm={async () => {
          const res = await adminApi.deleteNode(deleting.level, deleting.node.id);
          toast.success(res.message);
          await refresh();
        }}
      />
    </>
  );
}
