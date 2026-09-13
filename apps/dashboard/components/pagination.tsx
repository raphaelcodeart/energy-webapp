"use client";

import { useState } from "react";

export const DEFAULT_PAGE_SIZE = 25;
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

/** Client-side pagination over an already-fetched array.
 *
 * Deliberately client-side: every list this backs is fetched in full by an
 * endpoint that returns a plain array (GET /customers, /network/agents,
 * /contracts, ...). At current volumes (tens of rows) that is the right
 * trade -- server-side paging would mean changing those endpoints' response
 * shape and every caller for no user-visible gain. **The threshold to
 * revisit is roughly a few thousand rows in any one list**: past that the
 * payload itself becomes the problem and paging has to move into the SQL
 * (LIMIT/OFFSET + a COUNT), at which point this hook's API can stay and
 * only its internals change.
 *
 * No effects, everything derived: `page` is clamped at render time rather
 * than corrected in a useEffect. That matters because filtering can shrink
 * the list under a user who is on page 9 -- deriving means they simply see
 * the last valid page, with no flash of an empty table and no
 * setState-in-effect (which this codebase's lint rejects). */
export function usePagination<T>(items: T[], defaultPageSize: number = DEFAULT_PAGE_SIZE) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(defaultPageSize);

  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  // Clamped, never stored -- see the docstring above.
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const startIndex = (currentPage - 1) * pageSize;
  const pageItems = items.slice(startIndex, startIndex + pageSize);

  function changePageSize(next: number) {
    setPageSize(next);
    // Jump back to the top: keeping the page number while the window grows
    // would silently skip rows the user was about to read.
    setPage(1);
  }

  return {
    pageItems,
    page: currentPage,
    setPage,
    pageSize,
    setPageSize: changePageSize,
    total,
    totalPages,
    // 1-based, inclusive, for "Mostrati X-Y di Z". Both 0 when empty.
    firstShown: total === 0 ? 0 : startIndex + 1,
    lastShown: Math.min(startIndex + pageSize, total),
  };
}

/** Page numbers to render, with `null` marking an ellipsis gap. Always
    includes the first and last page plus a window around the current one,
    so the control stays a fixed width no matter how many pages there are. */
function pageNumbers(current: number, totalPages: number): (number | null)[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
  const pages = new Set<number>([1, totalPages, current, current - 1, current + 1]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= totalPages).sort((a, b) => a - b);
  const out: (number | null)[] = [];
  let previous = 0;
  for (const p of sorted) {
    if (previous && p - previous > 1) out.push(null);
    out.push(p);
    previous = p;
  }
  return out;
}

type PaginationProps = Pick<
  ReturnType<typeof usePagination<unknown>>,
  "page" | "setPage" | "pageSize" | "setPageSize" | "total" | "totalPages" | "firstShown" | "lastShown"
> & {
  /** What's being counted, for the summary line ("clienti", "contratti"...). */
  label?: string;
};

/** The standard list navigator: how many of how many, page controls, and a
    per-page selector. Renders nothing at all when everything already fits
    on one page -- a paging bar under a 5-row table is just noise. */
export function Pagination({
  page, setPage, pageSize, setPageSize, total, totalPages, firstShown, lastShown, label = "risultati",
}: PaginationProps) {
  if (total === 0) return null;
  const onlyOnePage = totalPages <= 1;
  // The per-page selector is still worth showing on a single page once the
  // list is big enough that the user might want fewer rows at a time.
  if (onlyOnePage && total <= PAGE_SIZE_OPTIONS[0]!) return null;

  const buttonBase =
    "min-w-[32px] h-8 px-2 rounded-lg text-xs font-semibold border transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed";
  const inactive =
    "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10";

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
      <p className="text-xs text-slate-400 light:text-slate-500">
        Mostrati <strong className="text-white light:text-slate-900">{firstShown}-{lastShown}</strong> di{" "}
        <strong className="text-white light:text-slate-900">{total}</strong> {label}
        {!onlyOnePage && (
          <span className="text-slate-500"> · pagina {page} di {totalPages}</span>
        )}
      </p>

      <div className="flex items-center gap-3">
        {!onlyOnePage && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage(page - 1)}
              disabled={page <= 1}
              aria-label="Pagina precedente"
              className={`${buttonBase} ${inactive}`}
            >
              ‹
            </button>
            {pageNumbers(page, totalPages).map((p, i) =>
              p === null ? (
                <span key={`gap-${i}`} className="px-1 text-xs text-slate-600 select-none">…</span>
              ) : (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPage(p)}
                  aria-current={p === page ? "page" : undefined}
                  className={`${buttonBase} ${
                    p === page ? "bg-orange-600 border-orange-600 text-white" : inactive
                  }`}
                >
                  {p}
                </button>
              )
            )}
            <button
              type="button"
              onClick={() => setPage(page + 1)}
              disabled={page >= totalPages}
              aria-label="Pagina successiva"
              className={`${buttonBase} ${inactive}`}
            >
              ›
            </button>
          </div>
        )}

        <label className="flex items-center gap-1.5 text-xs text-slate-400 light:text-slate-500">
          <span className="hidden sm:inline">Per pagina</span>
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="rounded-lg glass-input px-2 py-1 text-xs bg-slate-900 light:bg-white focus:border-orange-500 cursor-pointer"
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}
