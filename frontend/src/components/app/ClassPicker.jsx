import { useEffect, useId, useMemo, useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/app/Notice";
import { ClassPath } from "@/components/app/ClassPath";
import { findSection, useAcademicTree } from "@/hooks/useAcademicTree";
import { cn } from "@/lib/utils";

const OTHER = "__other__";
const KEYS = ["branch", "department", "year", "section"];
const TYPED = {
  branch: { placeholder: "e.g. Mechanical", maxLength: 40 },
  department: { placeholder: "e.g. Robotics", maxLength: 40 },
  year: { placeholder: "e.g. 3rd Year", maxLength: 12 },
  section: { placeholder: "e.g. A", maxLength: 1 },
};

/** Request-body fields for the picked class: a listed section, or a typed one (`custom_class`). */
export function classPayload(sectionId, info) {
  return info?.custom ? { custom_class: info.custom } : { section_id: Number(sectionId) };
}

/**
 * Cascading Branch -> Department -> Year -> Section picker backed by GET /api/academic/tree.
 * Emits the `section_id` the API expects, plus a description of the chosen class.
 *
 *   const [sectionId, setSectionId] = useState("");
 *   <ClassPicker value={sectionId} onChange={(id, info) => setSectionId(id)} error={errors.section_id} />
 *
 * onChange(sectionId | "", info | null)   info = { section_id, branch, department, year, section, label }
 * With `allowCustom`, every level also offers "Other (type your own)". A fully typed class is emitted as
 * onChange("", { custom: { branch, department, year, section }, label }); send it with `classPayload`.
 * `tree` is optional (pass one you already have); otherwise the picker fetches and caches it itself.
 */
export function ClassPicker({ value = "", onChange, tree: treeProp, disabled = false, error, className, showSummary = true, allowCustom = false }) {
  const uid = useId().replace(/:/g, "");
  const query = useAcademicTree({ enabled: !treeProp });
  const tree = treeProp || query.data;

  const initial = useMemo(() => findSection(tree, value), [tree, value]);
  const [branchId, setBranchId] = useState("");
  const [deptId, setDeptId] = useState("");
  const [yearId, setYearId] = useState("");
  const [otherAt, setOtherAt] = useState(-1); // first level the user is typing instead of choosing
  const [typed, setTyped] = useState({});
  const [customSel, setCustomSel] = useState(null);

  // Hydrate from an incoming value (editing an existing class, or the tree arriving after the value).
  useEffect(() => {
    if (initial) {
      setBranchId(String(initial.ids.branch));
      setDeptId(String(initial.ids.department));
      setYearId(String(initial.ids.year));
    }
  }, [initial]);

  const branch = tree?.branches?.find((b) => String(b.id) === branchId);
  const department = branch?.departments?.find((d) => String(d.id) === deptId);
  const year = department?.years?.find((y) => String(y.id) === yearId);
  const info = findSection(tree, value);

  const emit = (sectionId, detail) => onChange?.(sectionId, detail);

  if (!treeProp && query.isPending) {
    return (
      <div className={cn("grid gap-4 @lg:grid-cols-2", className)} role="status" aria-busy="true">
        <span className="sr-only">Loading classes</span>
        {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[4.75rem] w-full rounded-lg" />)}
      </div>
    );
  }
  if (!treeProp && query.isError) {
    return (
      <Notice tone="danger" title="Could not load the class list">
        <p>{query.error?.message}</p>
        <Button type="button" variant="outline" size="sm" className="mt-2" onClick={() => query.refetch()}>Try again</Button>
      </Notice>
    );
  }
  if (!tree?.branches?.length && !allowCustom) {
    return (
      <Notice tone="warning" title="No classes are open for registration yet">
        Admin has not created any classes. Please try again later.
      </Notice>
    );
  }

  const levels = [
    { key: "branch", label: "Branch", options: tree?.branches || [], value: branchId, placeholder: "Select branch", disabled: false },
    { key: "department", label: "Department", options: branch?.departments || [], value: deptId, placeholder: "Select department", disabled: !branch },
    { key: "year", label: "Year", options: department?.years || [], value: yearId, placeholder: "Select year", disabled: !department },
    { key: "section", label: "Section", options: year?.sections || [], value: info ? String(info.section_id) : "", placeholder: "Select section", disabled: !year },
  ];

  // Emit the typed class once every level has a name (chosen levels above `at` + typed levels from `at`).
  function pushCustom(at, nextTyped) {
    const chosen = [branch?.name, department?.name, year?.name];
    const names = KEYS.map((k, i) => (i >= at ? (nextTyped[k] || "").trim() : chosen[i]));
    if (at >= 0 && names.every(Boolean)) {
      const custom = { branch: names[0], department: names[1], year: names[2], section: names[3] };
      setCustomSel(custom);
      emit("", { custom, label: names.join(" → ") });
    } else {
      setCustomSel(null);
      emit("", null);
    }
  }

  function choose(level, next) {
    const idx = KEYS.indexOf(level);
    if (next === OTHER) {
      setOtherAt(idx);
      setTyped({});
      if (idx === 0) { setDeptId(""); setYearId(""); } else if (idx === 1) setYearId("");
      pushCustom(idx, {});
      return;
    }
    setOtherAt(-1);
    setTyped({});
    setCustomSel(null);
    if (level === "branch") { setBranchId(next); setDeptId(""); setYearId(""); emit("", null); }
    else if (level === "department") { setDeptId(next); setYearId(""); emit("", null); }
    else if (level === "year") { setYearId(next); emit("", null); }
    else {
      const id = Number(next);
      emit(id, {
        section_id: id,
        branch: branch?.name,
        department: department?.name,
        year: year?.name,
        section: year?.sections.find((s) => s.id === id)?.name,
        label: `${branch?.name} → ${department?.name} → ${year?.name} → ${year?.sections.find((s) => s.id === id)?.name}`,
      });
    }
  }

  function type(key, text) {
    const nextTyped = { ...typed, [key]: text };
    setTyped(nextTyped);
    pushCustom(otherAt, nextTyped);
  }

  const summary = customSel || info;

  return (
    <div className={className}>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,12rem),1fr))] gap-x-4 gap-y-4">
        {levels.map((lv, i) => {
          const id = `${uid}-${lv.key}`;
          const typing = otherAt >= 0 && i >= otherAt;
          const inputOnly = otherAt >= 0 && i > otherAt;
          return (
            <div key={lv.key} className="min-w-0">
              <Label htmlFor={id} className="mb-2 text-sm font-medium text-ink-2">{lv.label}</Label>
              {inputOnly ? null : (
                <Select value={i === otherAt ? OTHER : lv.value} onValueChange={(v) => choose(lv.key, v)} disabled={disabled || lv.disabled}>
                  <SelectTrigger id={id} className="w-full" aria-invalid={lv.key === "section" && error ? true : undefined}>
                    <SelectValue placeholder={lv.placeholder} />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    {lv.options.map((o) => <SelectItem key={o.id} value={String(o.id)}>{o.name}</SelectItem>)}
                    {allowCustom ? <SelectItem value={OTHER}>Other (type your own)</SelectItem> : null}
                  </SelectContent>
                </Select>
              )}
              {typing ? (
                <Input
                  id={inputOnly ? id : undefined}
                  aria-label={`Your ${lv.label.toLowerCase()}`}
                  className={inputOnly ? undefined : "mt-2"}
                  placeholder={TYPED[lv.key].placeholder}
                  maxLength={TYPED[lv.key].maxLength}
                  autoComplete="off"
                  disabled={disabled}
                  value={typed[lv.key] || ""}
                  onChange={(e) => type(lv.key, e.target.value)}
                />
              ) : null}
            </div>
          );
        })}
      </div>
      {error ? <p role="alert" className="mt-2 text-[0.8125rem] font-medium text-danger-ink">{error}</p> : null}
      {showSummary ? (
        <p aria-live="polite" className="mt-4 flex min-h-[2.4rem] items-center gap-2 rounded-lg border border-dashed border-line-strong px-3.5 py-2.5 text-[0.9375rem] text-muted-foreground">
          {summary ? (
            <>
              <span className="shrink-0">Your class:</span>
              <ClassPath cls={summary} />
            </>
          ) : (
            "Pick a branch, department, year and section."
          )}
        </p>
      ) : null}
    </div>
  );
}
