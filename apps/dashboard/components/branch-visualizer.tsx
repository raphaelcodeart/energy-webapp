"use client";

import { useState } from "react";
import type { BranchMemberRead } from "@/lib/types";

interface TreeNode {
  agent_id: string;
  depth: number;
  children: TreeNode[];
}

function buildTree(members: BranchMemberRead[]): TreeNode | null {
  if (!members || members.length === 0) return null;

  const first = members[0];
  if (!first) return null;

  // We assume the list is in traversal order where the parent of a node at depth D 
  // is the most recently seen node at depth D-1.
  const root: TreeNode = { agent_id: first.agent_id, depth: first.depth, children: [] };
  const stack: TreeNode[] = [root];

  for (let i = 1; i < members.length; i++) {
    const member = members[i];
    if (!member) continue;
    const node: TreeNode = { agent_id: member.agent_id, depth: member.depth, children: [] };

    while (stack.length > 0) {
      const topNode = stack[stack.length - 1];
      if (topNode && topNode.depth >= member.depth) {
        stack.pop();
      } else {
        break;
      }
    }

    const parentNode = stack[stack.length - 1];
    if (parentNode) {
      parentNode.children.push(node);
    }
    stack.push(node);
  }

  return root;
}

export function BranchVisualizer({ members }: { members: BranchMemberRead[] }) {
  const rootNode = buildTree(members);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyToClipboard = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  if (!rootNode) {
    return <p className="text-sm text-slate-500">Nessun membro della rete da visualizzare.</p>;
  }

  return (
    <div className="glass-card rounded-2xl p-6 border-white/5 bg-slate-950/40">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-white">Visualizzazione Albero Rete</h3>
          <p className="text-xs text-slate-400">Struttura gerarchica dei tuoi promoter affiliati</p>
        </div>
        <span className="px-3 py-1 text-xs font-semibold rounded-full bg-violet-500/10 text-violet-400 border border-violet-500/20">
          {members.length} Agenti Totali
        </span>
      </div>

      <div className="overflow-x-auto pb-4">
        <div className="min-w-[600px] p-2">
          <TreeNodeRenderer 
            node={rootNode} 
            isLast={true} 
            onCopy={copyToClipboard}
            copiedId={copiedId}
          />
        </div>
      </div>
    </div>
  );
}

function TreeNodeRenderer({ 
  node, 
  isLast, 
  onCopy, 
  copiedId 
}: { 
  node: TreeNode; 
  isLast: boolean; 
  onCopy: (id: string) => void;
  copiedId: string | null;
}) {
  const [isOpen, setIsOpen] = useState(true);
  const hasChildren = node.children.length > 0;

  // Heuristics for visual decorations based on depth
  const getDepthStyles = (depth: number) => {
    switch (depth) {
      case 0:
        return {
          bg: "bg-violet-500/20 border-violet-500/40 text-violet-300",
          label: "Tu (Root)",
        };
      case 1:
        return {
          bg: "bg-cyan-500/20 border-cyan-500/40 text-cyan-300",
          label: "Livello 1 (Diretto)",
        };
      default:
        return {
          bg: "bg-slate-800 border-slate-700 text-slate-300",
          label: `Livello ${depth}`,
        };
    }
  };

  const depthStyle = getDepthStyles(node.depth);

  return (
    <div className="flex flex-col relative pl-6">
      {/* Visual connection lines */}
      <div className="absolute left-0 top-0 bottom-0 w-px bg-slate-800" />
      <div className="absolute left-0 top-5 w-5 h-px bg-slate-800" />

      <div className="flex items-center gap-3 py-2">
        {/* Collapse / Expand toggle button */}
        {hasChildren ? (
          <button 
            onClick={() => setIsOpen(!isOpen)} 
            className="w-5 h-5 flex items-center justify-center rounded bg-slate-800 hover:bg-slate-700 text-white text-xs border border-white/5 transition cursor-pointer"
          >
            {isOpen ? "−" : "+"}
          </button>
        ) : (
          <div className="w-5 h-5 flex items-center justify-center">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-600" />
          </div>
        )}

        {/* Node card */}
        <div className="flex items-center gap-4 px-4 py-2.5 rounded-xl bg-slate-900/60 border border-white/5 hover:border-white/10 transition-all duration-200">
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-slate-300 tracking-tight">
                {node.agent_id.substring(0, 8)}...{node.agent_id.substring(node.agent_id.length - 8)}
              </span>
              <button
                onClick={() => onCopy(node.agent_id)}
                className="p-1 hover:bg-white/5 rounded text-slate-400 hover:text-white transition cursor-pointer"
                title="Copia UUID completo"
              >
                {copiedId === node.agent_id ? (
                  <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                  </svg>
                )}
              </button>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className={`px-2 py-0.5 text-[10px] font-bold rounded-md uppercase border ${depthStyle.bg}`}>
                {depthStyle.label}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Children rendering */}
      {hasChildren && isOpen && (
        <div className="flex flex-col ml-2 border-l border-dashed border-slate-800 pl-2">
          {node.children.map((child, idx) => (
            <TreeNodeRenderer
              key={child.agent_id}
              node={child}
              isLast={idx === node.children.length - 1}
              onCopy={onCopy}
              copiedId={copiedId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
