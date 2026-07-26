"use client";

import { useState } from "react";

export interface TreeNode {
  agent_id: string;
  depth: number;
  display_name: string;
  promoter_code: string;
  status: string;
  rank_code: string | null;
  children: TreeNode[];
}

// "Mario Rossi" -> "Mario R." -- full given name, surname reduced to initial,
// so nested tree cards stay compact.
export function formatShortName(displayName: string): string {
  const parts = displayName.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return displayName;
  const given = parts.slice(0, -1).join(" ");
  const surnameInitial = parts[parts.length - 1]!.charAt(0).toUpperCase();
  return `${given} ${surnameInitial}.`;
}

// One distinct color per network depth, so the level a node belongs to is
// recognizable at a glance without reading the badge text. Root gets its own
// color; levels 1-12 (the career-plan depth cap) cycle through 12 accents.
const ROOT_COLOR = {
  chip: "bg-violet-500/20 border-violet-500/40 text-violet-300",
  rail: "border-violet-500/50",
  dot: "bg-violet-400",
};

const LEVEL_COLORS = [
  { chip: "bg-cyan-500/20 border-cyan-500/40 text-cyan-300", rail: "border-cyan-500/50", dot: "bg-cyan-400" },
  { chip: "bg-emerald-500/20 border-emerald-500/40 text-emerald-300", rail: "border-emerald-500/50", dot: "bg-emerald-400" },
  { chip: "bg-amber-500/20 border-amber-500/40 text-amber-300", rail: "border-amber-500/50", dot: "bg-amber-400" },
  { chip: "bg-rose-500/20 border-rose-500/40 text-rose-300", rail: "border-rose-500/50", dot: "bg-rose-400" },
  { chip: "bg-indigo-500/20 border-indigo-500/40 text-indigo-300", rail: "border-indigo-500/50", dot: "bg-indigo-400" },
  { chip: "bg-pink-500/20 border-pink-500/40 text-pink-300", rail: "border-pink-500/50", dot: "bg-pink-400" },
  { chip: "bg-teal-500/20 border-teal-500/40 text-teal-300", rail: "border-teal-500/50", dot: "bg-teal-400" },
  { chip: "bg-orange-500/20 border-orange-500/40 text-orange-300", rail: "border-orange-500/50", dot: "bg-orange-400" },
  { chip: "bg-lime-500/20 border-lime-500/40 text-lime-300", rail: "border-lime-500/50", dot: "bg-lime-400" },
  { chip: "bg-fuchsia-500/20 border-fuchsia-500/40 text-fuchsia-300", rail: "border-fuchsia-500/50", dot: "bg-fuchsia-400" },
  { chip: "bg-sky-500/20 border-sky-500/40 text-sky-300", rail: "border-sky-500/50", dot: "bg-sky-400" },
  { chip: "bg-red-500/20 border-red-500/40 text-red-300", rail: "border-red-500/50", dot: "bg-red-400" },
];

export function getDepthStyle(depth: number): { chip: string; rail: string; dot: string; label: string } {
  if (depth === 0) return { ...ROOT_COLOR, label: "Tu" };
  if (depth === 1) return { ...LEVEL_COLORS[0]!, label: "Livello 1 · Diretto" };
  const color = LEVEL_COLORS[(depth - 1) % LEVEL_COLORS.length]!;
  return { ...color, label: `Livello ${depth}` };
}

const STATUS_DOT: Record<string, string> = {
  ACTIVE: "bg-emerald-400",
  SUSPENDED: "bg-amber-400",
  TERMINATED: "bg-rose-400",
};

export function LevelLegend({ maxDepth }: { maxDepth: number }) {
  const legendDepths = Array.from({ length: maxDepth + 1 }, (_, i) => i);
  return (
    <div className="flex flex-wrap items-center gap-2 mb-6 pb-4 border-b border-white/5 light:border-slate-200">
      {legendDepths.map((depth) => {
        const style = getDepthStyle(depth);
        return (
          <span
            key={depth}
            className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] font-bold border ${style.chip}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
            {style.label}
          </span>
        );
      })}
    </div>
  );
}

export function TreeNodeRenderer({
  node,
  onCopy,
  copiedId,
  defaultOpen = true,
}: {
  node: TreeNode;
  onCopy: (id: string) => void;
  copiedId: string | null;
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const hasChildren = node.children.length > 0;
  const depthStyle = getDepthStyle(node.depth);

  return (
    <div className="flex flex-col relative pl-6">
      {/* Visual connection lines */}
      <div className="absolute left-0 top-0 bottom-0 w-px bg-slate-800 light:bg-slate-100" />
      <div className="absolute left-0 top-5 w-5 h-px bg-slate-800 light:bg-slate-100" />

      <div className="flex items-center gap-3 py-2">
        {/* Collapse / Expand toggle button */}
        {hasChildren ? (
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="w-5 h-5 flex items-center justify-center rounded bg-slate-800 light:bg-slate-100 hover:bg-slate-700 text-white light:text-slate-900 text-xs border border-white/5 light:border-slate-200 transition cursor-pointer"
          >
            {isOpen ? "−" : "+"}
          </button>
        ) : (
          <div className="w-5 h-5 flex items-center justify-center">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-600 light:bg-slate-300" />
          </div>
        )}

        {/* Node card -- left rail colored by depth so the level reads at a glance */}
        <div
          className={`flex items-center gap-3 pl-3 pr-4 py-2.5 rounded-xl bg-slate-900/60 light:bg-slate-50 border-l-4 border border-white/5 light:border-slate-200 hover:border-white/10 transition-all duration-200 ${depthStyle.rail}`}
        >
          <span className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[node.status] ?? "bg-slate-500"}`} title={node.status} />

          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-semibold text-white light:text-slate-900 truncate">
                {formatShortName(node.display_name)}
              </span>
              <span className={`px-2 py-0.5 text-[10px] font-bold rounded-md border ${depthStyle.chip}`}>
                {depthStyle.label}
              </span>
              {node.rank_code && (
                <span className="px-2 py-0.5 text-[10px] font-bold rounded-md border bg-white/5 light:bg-slate-900/5 text-slate-300 light:text-slate-600 border-white/10 light:border-slate-300">
                  {node.rank_code}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="font-mono text-[10px] text-slate-500">{node.promoter_code}</span>
              <button
                onClick={() => onCopy(node.agent_id)}
                className="p-0.5 hover:bg-white/5 rounded text-slate-500 hover:text-white transition cursor-pointer"
                title="Copia UUID completo"
              >
                {copiedId === node.agent_id ? (
                  <svg className="w-3 h-3 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Children rendering */}
      {hasChildren && isOpen && (
        <div className="flex flex-col ml-2 border-l border-dashed border-slate-800 light:border-slate-200 pl-2">
          {node.children.map((child) => (
            <TreeNodeRenderer
              key={child.agent_id}
              node={child}
              onCopy={onCopy}
              copiedId={copiedId}
              defaultOpen={defaultOpen}
            />
          ))}
        </div>
      )}
    </div>
  );
}
