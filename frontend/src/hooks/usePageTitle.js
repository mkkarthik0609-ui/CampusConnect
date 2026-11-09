import { useMeta, SITE_NAME } from "@/hooks/useMeta";

export const APP_NAME = SITE_NAME;

/**
 * Sets the document title ("<title> | CampusConnect") plus the matching head tags via useMeta.
 * <PageHeader title="..."/> calls this for you; an empty title on "/" gives the landing-page head.
 */
export function usePageTitle(title) {
  useMeta({ title });
}
