import { useQuery } from "@tanstack/react-query";
import { metaApi } from "@/lib/endpoints";

/** GET /api/meta: public app metadata. */
export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: metaApi.get, staleTime: 10 * 60_000, retry: false });
}
