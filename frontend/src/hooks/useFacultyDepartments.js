import { useQuery } from "@tanstack/react-query";
import { authApi } from "@/lib/endpoints";

/** Active department names for the faculty signup select. */
export function useFacultyDepartments() {
  return useQuery({
    queryKey: ["academic", "faculty-departments"],
    queryFn: authApi.facultyDepartments,
    staleTime: 5 * 60_000,
    select: (d) => d.items || [],
  });
}
