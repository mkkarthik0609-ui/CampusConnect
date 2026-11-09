import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { metaApi } from "@/lib/endpoints";

export const SITE_URL = "https://campus-connect-network.vercel.app";
export const SITE_NAME = "CampusConnect";
const HOME_TITLE = `${SITE_NAME} | Mentor chat, meetings and classes for your college`;
const DEFAULT_DESCRIPTION =
  "CampusConnect connects students, faculty and administrators: mentor chat, meeting requests with timing set by faculty, and admin-defined classes for your college.";
const OG_IMAGE = `${SITE_URL}/og-image.png`;

/** Structured data for the landing page only. */
const HOME_JSON_LD = {
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "WebSite", "@id": `${SITE_URL}/#website`, url: `${SITE_URL}/`, name: SITE_NAME, description: DEFAULT_DESCRIPTION, inLanguage: "en" },
    {
      "@type": "EducationalOrganization", "@id": `${SITE_URL}/#org`, name: SITE_NAME, url: `${SITE_URL}/`,
      logo: `${SITE_URL}/icon-512.png`, description: DEFAULT_DESCRIPTION,
    },
    {
      "@type": "SoftwareApplication", name: SITE_NAME, url: `${SITE_URL}/`, applicationCategory: "EducationApplication",
      operatingSystem: "Any (web browser)", description: DEFAULT_DESCRIPTION, publisher: { "@id": `${SITE_URL}/#org` },
    },
  ],
};

function upsert(selector, create, content) {
  let el = document.head.querySelector(selector);
  if (content == null || content === "") { el?.remove(); return; }
  if (!el) { el = create(); document.head.appendChild(el); }
  return el;
}

function setMeta(attr, key, content) {
  const el = upsert(`meta[${attr}="${key}"]`, () => { const m = document.createElement("meta"); m.setAttribute(attr, key); return m; }, content);
  el?.setAttribute("content", content);
}

function setCanonical(href) {
  const el = upsert('link[rel="canonical"]', () => { const l = document.createElement("link"); l.rel = "canonical"; return l; }, href);
  if (el) el.href = href;
}

function setJsonLd(data) {
  const id = "cc-jsonld";
  document.getElementById(id)?.remove();
  if (!data) return;
  const s = document.createElement("script");
  s.id = id;
  s.type = "application/ld+json"; // data block: never executed, so the CSP (script-src 'self') does not apply
  s.textContent = JSON.stringify(data);
  document.head.appendChild(s);
}

/**
 * Per-route <head>: title ("Page | CampusConnect"), description, canonical, Open Graph, Twitter, robots, JSON-LD.
 *   useMeta({ title: "Sign in", description: "..." })
 * Only "/" is indexable (index,follow, canonical, JSON-LD); every other route gets noindex,nofollow and no canonical
 * unless `robots` says otherwise. `path` defaults to the current location. The index.html defaults cover crawlers
 * that do not run JavaScript.
 */
export function useMeta({ title, description, path, robots, image, jsonLd } = {}) {
  const ld = jsonLd === undefined ? undefined : JSON.stringify(jsonLd);
  useEffect(() => {
    const pathname = path ?? window.location.pathname;
    const home = pathname === "/";
    const isIndexable = (robots || (home ? "index,follow" : "noindex,nofollow")).startsWith("index");
    const fullTitle = title ? `${title} | ${SITE_NAME}` : home ? HOME_TITLE : SITE_NAME;
    const desc = description || DEFAULT_DESCRIPTION;
    const url = `${SITE_URL}${pathname}`;
    const img = image || OG_IMAGE;

    document.title = fullTitle;
    setMeta("name", "description", desc);
    setMeta("name", "robots", robots || (home ? "index,follow" : "noindex,nofollow"));
    setCanonical(isIndexable ? url : "");
    setMeta("property", "og:type", "website");
    setMeta("property", "og:site_name", SITE_NAME);
    setMeta("property", "og:title", fullTitle);
    setMeta("property", "og:description", desc);
    setMeta("property", "og:url", url);
    setMeta("property", "og:image", img);
    setMeta("name", "twitter:card", "summary_large_image");
    setMeta("name", "twitter:title", fullTitle);
    setMeta("name", "twitter:description", desc);
    setMeta("name", "twitter:image", img);
    setJsonLd(ld !== undefined ? JSON.parse(ld) : home ? HOME_JSON_LD : null);
    return () => setJsonLd(null);
  }, [title, description, path, robots, image, ld]);
}

/** GET /api/meta: public app metadata from the backend (was `useMeta` before the head hook took the name). */
export function useAppMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: metaApi.get, staleTime: 10 * 60_000, retry: false });
}
