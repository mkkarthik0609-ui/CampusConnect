/**
 * refetchInterval helper: poll every `ms`, but back off exponentially (capped at 60 s) while the query is in error.
 * react-query already pauses interval polling in hidden tabs unless refetchIntervalInBackground is set.
 *   useQuery({ ..., refetchInterval: (q) => pollEvery(30_000, q) })
 */
export function pollEvery(ms, query) {
  if (!ms) return false;
  const failures = query?.state?.status === "error" ? Math.min(query.state.errorUpdateCount || 1, 5) : 0;
  return Math.min(ms * 2 ** failures, 60_000);
}
