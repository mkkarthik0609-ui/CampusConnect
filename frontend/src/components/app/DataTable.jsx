import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/app/EmptyState";
import { Notice } from "@/components/app/Notice";
import { cn } from "@/lib/utils";

/**
 * Table on desktop, stack of labelled cards below 40rem (no horizontal scrolling on phones).
 *
 *   <DataTable
 *     caption="Students in this class"                  // screen-reader name for the table
 *     rows={data.items}
 *     rowKey={(r) => r.id}
 *     loading={query.isPending}
 *     error={query.error}                                // ApiError | Error | null
 *     empty={{ title: "No students yet", children: "They appear here once they register." }}
 *     columns={[
 *       { key: "name", header: "Name", cell: (r) => <strong>{r.full_name}</strong>, primary: true },
 *       { key: "usn", header: "USN", cell: (r) => <span className="font-mono">{r.usn}</span> },
 *       { key: "actions", header: <span className="sr-only">Actions</span>, label: "", align: "right", cell: (r) => <Button size="sm">Open</Button> },
 *     ]}
 *   />
 *
 * Column fields: key, header (node), cell(row) (defaults to row[key]), label (mobile caption, defaults to the
 * header text; "" hides it), align ("right"), className (applies to th and td), primary (mobile: shown as the
 * card title with no label).
 */
export function DataTable({ columns, rows, rowKey = (r) => r.id, caption, loading = false, error, empty, skeletonRows = 4, onRowClick, className }) {
  if (error) {
    return <Notice tone="danger" title="Could not load this list">{error.message || "Please try again in a moment."}</Notice>;
  }

  const showEmpty = !loading && (!rows || rows.length === 0);
  if (showEmpty) {
    return (
      <div className={cn("rounded-lg border bg-card shadow-sm", className)}>
        <EmptyState {...(empty || { title: "Nothing here yet" })} />
      </div>
    );
  }

  return (
    <div className={cn("overflow-hidden rounded-lg border bg-card shadow-sm max-sm:overflow-visible max-sm:rounded-none max-sm:border-0 max-sm:bg-transparent max-sm:shadow-none", className)}>
      <Table role="table" className="max-sm:block" aria-busy={loading || undefined}>
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <TableHeader role="rowgroup" className="max-sm:sr-only">
          <TableRow role="row">
            {columns.map((c) => (
              <TableHead key={c.key} role="columnheader" scope="col" className={cn(c.align === "right" && "text-right", c.className)}>
                {c.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody role="rowgroup" className="max-sm:block">
          {loading
            ? Array.from({ length: skeletonRows }, (_, i) => (
                <TableRow key={`s${i}`} role="row" className={rowMobile}>
                  {columns.map((c) => (
                    <TableCell key={c.key} role="cell" className={cellMobile}>
                      <Skeleton className="h-5 w-full max-w-40" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            : rows.map((row) => (
                <TableRow
                  key={rowKey(row)}
                  role="row"
                  className={cn(rowMobile, onRowClick && "cursor-pointer")}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {columns.map((c) => {
                    const label = c.label ?? (typeof c.header === "string" ? c.header : "");
                    return (
                      <TableCell
                        key={c.key}
                        role="cell"
                        data-label={c.primary ? "" : label}
                        className={cn(
                          cellMobile,
                          c.align === "right" && "text-right max-sm:justify-end",
                          c.primary && "max-sm:justify-start max-sm:pt-2 max-sm:text-left max-sm:text-base max-sm:font-semibold",
                          c.className,
                        )}
                      >
                        {c.cell ? c.cell(row) : row[c.key]}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
        </TableBody>
      </Table>
    </div>
  );
}

const rowMobile =
  "max-sm:mb-3 max-sm:block max-sm:rounded-lg max-sm:border max-sm:bg-card max-sm:px-4 max-sm:py-1.5 max-sm:shadow-sm max-sm:hover:bg-card";

const cellMobile =
  "max-sm:flex max-sm:items-start max-sm:justify-between max-sm:gap-3 max-sm:border-b max-sm:px-0 max-sm:py-2.5 max-sm:text-right last:max-sm:border-b-0 max-sm:before:max-w-[42%] max-sm:before:pt-0.5 max-sm:before:text-left max-sm:before:text-[0.8125rem] max-sm:before:font-semibold max-sm:before:text-muted-foreground max-sm:before:content-[attr(data-label)] max-sm:data-[label='']:before:hidden";
