"use client";

import type { CollaborationDocumentBlock, CollaborationDocumentRead } from "@/lib/types";

/** Renders one legal document supplied by the backend.
 *
 * The content arrives as structured blocks, never as markup: this is text the
 * server owns and a customer legally signs, so the component decides the
 * typography and nothing here ever interprets HTML. See
 * apps/api/app/domains/network/collaboration_documents.py.
 *
 * Adding a block type is the only reason to touch this file; adding or
 * changing a DOCUMENT requires no frontend change at all.
 */
function Block({ block }: { block: CollaborationDocumentBlock }) {
  switch (block.type) {
    case "heading":
      return (
        <h4 className="text-[13px] font-bold text-white light:text-slate-900 uppercase tracking-wide mt-5 first:mt-0 pb-1.5 border-b border-white/10 light:border-slate-200">
          {block.text}
        </h4>
      );

    case "paragraph":
      return <p className="text-[12px] leading-relaxed text-slate-300 light:text-slate-600 mt-2.5">{block.text}</p>;

    case "clause":
      // The clause number is what people actually cite ("ai sensi dell'art.
      // 3.4"), so it gets its own column instead of being swallowed by the
      // paragraph.
      return (
        <div className="flex gap-2.5 mt-2.5">
          <span className="shrink-0 font-mono text-[11px] font-bold text-orange-400 tabular-nums w-10">
            {block.number}
          </span>
          <p className="text-[12px] leading-relaxed text-slate-300 light:text-slate-600 flex-1">{block.text}</p>
        </div>
      );

    case "bullets":
      return (
        <ul className="mt-2 ml-12 space-y-1.5 list-disc marker:text-orange-400/60">
          {block.items.map((item, i) => (
            <li key={i} className="text-[12px] leading-relaxed text-slate-300 light:text-slate-600 pl-1">
              {item}
            </li>
          ))}
        </ul>
      );

    case "table":
      // Figures somebody is agreeing to have to be readable as a table.
      // Scrolls inside itself so a wide table never breaks the modal.
      return (
        <div className="mt-3">
          {block.caption && (
            <p className="text-[11px] font-semibold text-slate-400 light:text-slate-500 mb-1.5">{block.caption}</p>
          )}
          <div className="overflow-x-auto rounded-lg border border-white/10 light:border-slate-200">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="bg-white/5 light:bg-slate-900/5">
                  {block.columns.map((col, i) => (
                    <th
                      key={i}
                      className="py-2 px-3 text-[10px] font-bold uppercase tracking-wider text-slate-400 light:text-slate-500 whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 light:divide-slate-200">
                {block.rows.map((row, r) => (
                  <tr key={r}>
                    {row.map((cell, c) => (
                      <td
                        key={c}
                        className={`py-2 px-3 text-[12px] whitespace-nowrap ${
                          c === 0
                            ? "text-slate-300 light:text-slate-600 font-medium"
                            : "text-white light:text-slate-900 font-bold tabular-nums"
                        }`}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      );

    case "signature":
      return (
        <p className="mt-4 p-3 rounded-lg bg-orange-500/5 border border-orange-500/20 text-[11px] leading-relaxed text-orange-300/90 light:text-orange-700">
          {block.text}
        </p>
      );

    default:
      return null;
  }
}

export function CollaborationDocumentViewer({ document }: { document: CollaborationDocumentRead }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-1">
        <h3 className="text-sm font-bold text-white light:text-slate-900">{document.title}</h3>
        <span className="font-mono text-[10px] text-slate-500">v{document.version}</span>
      </div>
      <p className="text-[11px] text-slate-500 mb-3">{document.subtitle}</p>
      {/* Scrolls on its own so the checkbox and the OTP step below stay
          reachable without scrolling past the whole contract. */}
      <div className="max-h-72 overflow-y-auto rounded-xl bg-white/5 light:bg-slate-900/[0.03] border border-white/10 light:border-slate-200 p-4">
        {document.blocks.map((block, i) => (
          <Block key={i} block={block} />
        ))}
      </div>
    </div>
  );
}
