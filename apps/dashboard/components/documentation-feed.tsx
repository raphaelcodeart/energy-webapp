"use client";

import { useQuery } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { DocumentationPostRead } from "@/lib/types";

async function fetchFeed(): Promise<DocumentationPostRead[]> {
  const res = await fetch("/api/proxy/documentation");
  if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile caricare la documentazione."));
  return res.json();
}

/** Read-only news/documentation feed -- same content and audience-filtering
 * (see documentation/service.py audiences_for_roles) whether it's mounted from
 * the customer or the promoter dashboard, so a single shared component avoids
 * keeping two copies of this rendering logic in sync. */
export function DocumentationFeed() {
  const { data: posts, error, isLoading } = useQuery({
    queryKey: ["documentation", "feed"],
    queryFn: fetchFeed,
  });

  if (isLoading) {
    return <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 animate-pulse h-40" />;
  }
  if (error) {
    return <p className="text-sm text-rose-400">{(error as Error).message}</p>;
  }
  if (!posts || posts.length === 0) {
    return (
      <div className="glass-card rounded-2xl p-8 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 text-center text-sm text-slate-500">
        Non c&apos;è ancora nessuna news o documentazione disponibile.
      </div>
    );
  }

  return (
    <div className="grid gap-5 sm:grid-cols-2">
      {posts.map((p) => (
        <article
          key={p.id}
          className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden flex flex-col"
        >
          {p.image_url && (
            // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source uploaded photo
            <img src={p.image_url} alt="" className="w-full h-44 object-cover" />
          )}
          <div className="p-5 flex flex-col gap-2 flex-1">
            <h3 className="text-base font-bold text-white light:text-slate-900">{p.title}</h3>
            {p.body && (
              <p className="text-sm text-slate-300 light:text-slate-600 whitespace-pre-wrap">{p.body}</p>
            )}
            <div className="flex flex-wrap gap-2 mt-2">
              {p.video_url && (
                <a
                  href={p.video_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Guarda il video
                </a>
              )}
              {p.pdf_url && (
                <a
                  href={p.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H8a2 2 0 01-2-2V5a2 2 0 012-2h6l6 6v11a2 2 0 01-2 2z" />
                  </svg>
                  {p.pdf_filename ? `Scarica ${p.pdf_filename}` : "Scarica PDF"}
                </a>
              )}
            </div>
            <span className="text-[10px] text-slate-500 mt-auto pt-2">
              {new Date(p.created_at).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" })}
            </span>
          </div>
        </article>
      ))}
    </div>
  );
}
