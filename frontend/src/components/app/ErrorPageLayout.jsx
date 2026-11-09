import { Link, useInRouterContext } from "react-router-dom";
import { usePageTitle } from "@/hooks/usePageTitle";
import { Brand, BrandMark } from "@/components/app/BrandMark";
import { cn } from "@/lib/utils";

/**
 * Link that also works outside the router (the global error boundary in App.jsx renders above <RouterProvider>):
 * inside the router it is a client-side <Link>, outside it a plain <a> (full page load).
 */
export function PageLink({ to, children, ...rest }) {
  const inRouter = useInRouterContext();
  return inRouter ? <Link to={to} {...rest}>{children}</Link> : <a href={to} {...rest}>{children}</a>;
}

function Wordmark() {
  const inRouter = useInRouterContext();
  if (inRouter) return <Brand to="/" />;
  return (
    <a href="/" aria-label="CampusConnect home" className="inline-flex rounded-sm no-underline">
      <Brand asText />
    </a>
  );
}

/**
 * Shared look of the 403 / 404 / 500 / offline pages: the logo, a huge outlined display code, short copy, actions.
 * `standalone` adds a minimal header + <main> for use outside the AppShell (public 404, crashes, server unreachable);
 * inside the shell the shell already provides <main>.
 */
export function ErrorPageLayout({ code, title, children, actions, standalone = false, documentTitle }) {
  usePageTitle(documentTitle || `${code} ${title}`);
  const chars = String(code).split("");
  const body = (
    <section
      aria-labelledby="error-title"
      className={cn(
        "relative isolate grid content-center justify-items-center gap-5 py-14 text-center",
        standalone ? "min-h-[calc(100dvh-6rem)]" : "min-h-[62vh]",
      )}
    >
      {/* dotted field, fading out from the middle */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 [background-image:radial-gradient(var(--line-strong)_1px,transparent_1.2px)] [background-size:24px_24px] opacity-60 [mask-image:radial-gradient(ellipse_60%_55%_at_50%_45%,#000,transparent)]"
      />
      <BrandMark size={34} strokeWidth={5} className="text-muted-foreground" />
      <p aria-hidden="true" className="err-code">
        {chars.map((c, i) => <span key={i} className="err-in">{c}</span>)}
      </p>
      <h1 id="error-title" className="m-0 text-[clamp(1.6rem,1.2rem+1.8vw,2.5rem)] leading-[1.1] font-normal tracking-[-0.03em]">{title}</h1>
      <div className="grid max-w-[34rem] gap-2 text-[1.0625rem] text-muted-foreground">{children}</div>
      {actions ? <div className="mt-2 flex flex-wrap justify-center gap-3">{actions}</div> : null}
    </section>
  );

  if (!standalone) return body;
  return (
    <div className="min-h-dvh bg-background">
      <a className="skip-link" href="#main">Skip to main content</a>
      <header className="px-[clamp(1rem,4vw,3rem)] pt-6">
        <Wordmark />
      </header>
      <main id="main" tabIndex={-1} className="px-[clamp(1rem,4vw,3rem)]">
        {body}
      </main>
    </div>
  );
}
