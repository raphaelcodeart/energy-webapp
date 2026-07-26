"use client";

import { useState } from "react";
import type { BranchMemberRead } from "@/lib/types";
import { LevelLegend, TreeNodeRenderer, type TreeNode } from "@/components/network-tree";

function buildTree(members: BranchMemberRead[]): TreeNode | null {
  if (!members || members.length === 0) return null;

  const first = members[0];
  if (!first) return null;

  // We assume the list is in traversal order where the parent of a node at depth D
  // is the most recently seen node at depth D-1.
  const toNode = (m: BranchMemberRead): TreeNode => ({
    agent_id: m.agent_id,
    depth: m.depth,
    display_name: m.display_name,
    promoter_code: m.promoter_code,
    status: m.status,
    rank_code: m.rank_code,
    children: [],
  });

  const root: TreeNode = toNode(first);
  const stack: TreeNode[] = [root];

  for (let i = 1; i < members.length; i++) {
    const member = members[i];
    if (!member) continue;
    const node: TreeNode = toNode(member);

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

  const maxDepth = members.reduce((max, m) => Math.max(max, m.depth), 0);

  return (
    <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white light:text-slate-900">Visualizzazione Albero Rete</h3>
          <p className="text-xs text-slate-400 light:text-slate-500">Struttura gerarchica dei tuoi promoter affiliati</p>
        </div>
        <span className="px-3 py-1 text-xs font-semibold rounded-full bg-violet-500/10 text-violet-400 border border-violet-500/20 shrink-0">
          {members.length} Agenti Totali
        </span>
      </div>

      <LevelLegend maxDepth={maxDepth} />

      <div className="overflow-x-auto pb-4">
        <div className="min-w-[600px] p-2">
          <TreeNodeRenderer
            node={rootNode}
            onCopy={copyToClipboard}
            copiedId={copiedId}
          />
        </div>
      </div>
    </div>
  );
}
