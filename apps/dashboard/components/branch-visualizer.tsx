"use client";

import { useState } from "react";
import type { BranchMemberRead } from "@/lib/types";
import { LevelLegend, TreeNodeRenderer, type TreeNode } from "@/components/network-tree";
import { NetworkNodeDetailModal } from "@/components/network-node-detail-modal";

function buildTree(members: BranchMemberRead[]): TreeNode | null {
  if (!members || members.length === 0) return null;

  // Build strictly from parent_agent_id, not row order -- the API has no
  // guaranteed ORDER BY (it's a plain `WHERE id IN (...)`), so a previous
  // depth-stack-based reconstruction silently produced a broken tree
  // whenever Postgres didn't happen to return rows in pre-order. Every
  // BranchMemberRead is either the root (parent_agent_id null) or has a
  // parent that is itself present in this same list.
  const nodesById = new Map<string, TreeNode>();
  for (const m of members) {
    nodesById.set(m.agent_id, {
      agent_id: m.agent_id,
      depth: m.depth,
      display_name: m.display_name,
      promoter_code: m.promoter_code,
      status: m.status,
      rank_code: m.rank_code,
      children: [],
    });
  }

  let root: TreeNode | null = null;
  for (const m of members) {
    const node = nodesById.get(m.agent_id)!;
    if (m.parent_agent_id && nodesById.has(m.parent_agent_id)) {
      nodesById.get(m.parent_agent_id)!.children.push(node);
    } else {
      root = node; // no parent in this fetch -> this is the branch root
    }
  }
  // Children in a stable, readable order regardless of fetch order.
  for (const node of nodesById.values()) {
    node.children.sort((a, b) => a.display_name.localeCompare(b.display_name));
  }

  return root;
}

export function BranchVisualizer({ members }: { members: BranchMemberRead[] }) {
  const rootNode = buildTree(members);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<{ agentId: string; displayName: string } | null>(null);

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
            onNodeClick={(agentId, displayName) => setSelectedNode({ agentId, displayName })}
            startOpen
          />
        </div>
      </div>

      {selectedNode && (
        <NetworkNodeDetailModal
          agentId={selectedNode.agentId}
          displayName={selectedNode.displayName}
          onClose={() => setSelectedNode(null)}
        />
      )}
    </div>
  );
}
