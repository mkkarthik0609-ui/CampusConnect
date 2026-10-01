import { useQuery } from "@tanstack/react-query";
import { academicApi } from "@/lib/endpoints";
import { queryKeys } from "@/lib/queryClient";

/** Public class hierarchy (active rows only): { branches: [{ id, name, departments: [{ id, name, years: [{ id, name, sections: [{ id, name }] }] }] }] } */
export function useAcademicTree(options = {}) {
  return useQuery({
    queryKey: queryKeys.academicTree,
    queryFn: academicApi.tree,
    staleTime: 5 * 60_000,
    ...options,
  });
}

/** Locate a section in the tree -> { branch, department, year, section, ids } or null. */
export function findSection(tree, sectionId) {
  if (!tree || sectionId === "" || sectionId == null) return null;
  const target = Number(sectionId);
  for (const branch of tree.branches || []) {
    for (const department of branch.departments || []) {
      for (const year of department.years || []) {
        for (const section of year.sections || []) {
          if (section.id === target) {
            return {
              section_id: section.id,
              branch: branch.name,
              department: department.name,
              year: year.name,
              section: section.name,
              label: `${branch.name} → ${department.name} → ${year.name} → ${section.name}`,
              ids: { branch: branch.id, department: department.id, year: year.id, section: section.id },
            };
          }
        }
      }
    }
  }
  return null;
}

/** Unique department names across all branches (used by faculty signup). */
export function departmentNames(tree) {
  const names = new Set();
  for (const branch of tree?.branches || []) for (const d of branch.departments || []) names.add(d.name);
  return [...names].sort((a, b) => a.localeCompare(b));
}
