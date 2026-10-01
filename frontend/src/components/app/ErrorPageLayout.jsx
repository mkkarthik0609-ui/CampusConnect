import { usePageTitle } from "@/hooks/usePageTitle";
import { Brand } from "@/components/app/BrandMark";
import { cn } from "@/lib/utils";

/**
 * Shared look of the 403 / 404 / 500 pages. `standalone` adds a minimal header + <main> for use outside
 * the AppShell (public 404, server-unreachable screen); inside the shell the shell already provides <main>.
 */
export function ErrorPageLayout({ code, title, children, actions, standalone = false, documentTitle }) {
  usePageTitle(documentTitle || `${code} ${title}`);
  const digits = String(code).split("");
  const body = (
    <section aria-labelledby="error-title" className={cn("grid max-w-[34rem] content-center justify-items-start gap-3 py-12", !standalone && "min-h-[55vh]")}>
      <p aria-hidden="true" className="m-0 font-display text-[clamp(5rem,3rem+10vw,9rem)] leading-[0.85] font-extrabold tracking-[-0.04em] text-primary">
        {digits.map((d, i) => <span key={i} className={d === "0" && i === 1 ? "text-saffron" : undefined}>{d}</span>)}
      </p>
      <h1 id="error-title" className="m-0 mt-2 text-[clamp(1.6rem,1.25rem+1.5vw,2.15rem)] leading-[1.1]">{title}</h1>
      <div className="grid gap-2 text-[1.0625rem] text-muted-foreground">{children}</div>
      {actions ? <div className="mt-3 flex flex-wrap gap-2">{actions}</div> : null}
    </section>
  );

  if (!standalone) return body;
  return (
    <div className="min-h-dvh bg-background">
      <a className="skip-link" href="#main">Skip to main content</a>
      <header className="px-[clamp(1rem,4vw,3rem)] pt-6">
        <Brand to="/" wordClassName="text-ink" accentClassName="text-primary" />
      </header>
      <main id="main" tabIndex={-1} className="px-[clamp(1rem,4vw,3rem)]">
        {body}
      </main>
    </div>
  );
}
