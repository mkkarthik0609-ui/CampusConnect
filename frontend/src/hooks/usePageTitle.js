import { useEffect } from "react";

export const APP_NAME = "Campus Connect";

/** Sets document.title to "<title> · Campus Connect". <PageHeader title="..."/> calls this for you. */
export function usePageTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME;
  }, [title]);
}
