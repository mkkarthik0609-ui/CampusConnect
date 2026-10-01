import { Link } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { usePageTitle } from "@/hooks/usePageTitle";
import { cn } from "@/lib/utils";

/**
 * Title block at the top of every signed-in page. Renders the page's one <h1> and sets document.title.
 *
 *   <PageHeader title="Meetings" description="Requests and history." actions={<Button>Request</Button>} />
 *   <PageHeader title={<ClassPath cls={c} size="lg" />} documentTitle="Class 3rd Year A" back={{ to: "/faculty/classes", label: "My classes" }} />
 */
export function PageHeader({ title, description, actions, back, documentTitle, className }) {
  usePageTitle(documentTitle || (typeof title === "string" ? title : ""));
  return (
    <header className={cn("mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3", className)}>
      <div className="min-w-0">
        {back ? (
          <Link
            to={back.to}
            className="mb-2 inline-flex min-h-8 items-center gap-1 rounded-sm text-sm font-semibold text-muted-foreground no-underline hover:text-primary"
          >
            <ChevronLeft aria-hidden="true" className="size-4" />
            {back.label}
          </Link>
        ) : null}
        <h1 className="m-0 text-[clamp(1.6rem,1.25rem+1.5vw,2.15rem)] leading-[1.1]">{title}</h1>
        {description ? <p className="mt-2 max-w-[62ch] text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2 max-sm:w-full max-sm:[&>*]:flex-1">{actions}</div> : null}
    </header>
  );
}

/** Heading row inside a page: "Upcoming meetings ........ [View all]". */
export function SectionHeading({ title, actions, as: Tag = "h2", className }) {
  return (
    <div className={cn("mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2", className)}>
      <Tag className="m-0 text-[clamp(1.15rem,1.05rem+0.5vw,1.4rem)]">{title}</Tag>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
