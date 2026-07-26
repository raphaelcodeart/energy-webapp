"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { AgentListItemRead } from "@/lib/types";
import { LevelLegend, TreeNodeRenderer, type TreeNode } from "@/components/network-tree";
import { NetworkNodeDetailModal } from "@/components/network-node-detail-modal";

async function fetchAgents(): Promise<AgentListItemRead[]> {
  const res = await fetch("/api/proxy/network/agents");
  if (!res.ok) throw new Error("Impossibile caricare la rete commerciale.");
  return res.json();
}

// The org-wide agent list has no depth field (it's not scoped to one branch)
// -- depth is computed here by walking each agent's parent chain, and the
// forest can have more than one root (multiple independent top-level
// sponsors), unlike a single promoter's own branch view.
function buildForest(agents: AgentListItemRead[]): { roots: TreeNode[]; maxDepth: number } {
  const nodeById = new Map<string, TreeNode>(
    agents.map((a) => [
      a.id,
      {
        agent_id: a.id,
        depth: 0,
        display_name: a.display_name,
        promoter_code: a.promoter_code,
        status: a.status,
        rank_code: a.rank_code,
        children: [],
      },
    ])
  );

  const roots: TreeNode[] = [];
  for (const a of agents) {
    const node = nodeById.get(a.id)!;
    const parent = a.direct_parent_agent_id ? nodeById.get(a.direct_parent_agent_id) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }

  let maxDepth = 0;
  function assignDepth(node: TreeNode, depth: number) {
    node.depth = depth;
    maxDepth = Math.max(maxDepth, depth);
    for (const child of node.children) assignDepth(child, depth + 1);
  }
  roots.forEach((r) => assignDepth(r, 0));

  return { roots, maxDepth };
}

function countNodes(node: TreeNode): number {
  return 1 + node.children.reduce((sum, c) => sum + countNodes(c), 0);
}

export function AdminNetworkPanel() {
  const { data: agents, error: loadError, isLoading } = useQuery({
    queryKey: ["admin", "agents", "tree"],
    queryFn: fetchAgents,
  });
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [expandAll, setExpandAll] = useState(false);
  const [selectedNode, setSelectedNode] = useState<{ agentId: string; displayName: string } | null>(null);

  const copyToClipboard = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const { roots, maxDepth } = useMemo(() => buildForest(agents ?? []), [agents]);

  const filteredRoots = useMemo(() => {
    if (!search.trim()) return roots;
    const query = search.trim().toLowerCase();
    const matches = (node: TreeNode): boolean =>
      node.display_name.toLowerCase().includes(query) ||
      node.promoter_code.toLowerCase().includes(query) ||
      node.children.some(matches);
    function prune(node: TreeNode): TreeNode | null {
      const keptChildren = node.children.map(prune).filter((c): c is TreeNode => c !== null);
      const selfMatches =
        node.display_name.toLowerCase().includes(query) || node.promoter_code.toLowerCase().includes(query);
      if (!selfMatches && keptChildren.length === 0) return null;
      return { ...node, children: keptChildren };
    }
    return roots.map(prune).filter((r): r is TreeNode => r !== null);
  }, [roots, search]);

  if (isLoading) {
    return <p className="text-sm text-slate-500 text-center py-12">Caricamento rete commerciale...</p>;
  }

  if (loadError) {
    return <p className="text-sm text-rose-400">Impossibile caricare la rete commerciale.</p>;
  }

  return (
    <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="text-lg font-semibold text-white light:text-slate-900">Rete Commerciale</h3>
          <p className="text-xs text-slate-400 light:text-slate-500">
            Struttura gerarchica completa dell&apos;organizzazione, fino a {maxDepth} livelli di profondità
          </p>
        </div>
        <span className="px-3 py-1 text-xs font-semibold rounded-full bg-violet-500/10 text-violet-400 border border-violet-500/20 shrink-0">
          {agents?.length ?? 0} Agenti Totali
        </span>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="w-full sm:max-w-xs relative">
          <input
            type="text"
            placeholder="Cerca promoter o codice..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl glass-input pl-10 pr-4 py-2 text-xs focus:border-orange-500"
          />
          <svg className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <button
          onClick={() => setExpandAll((v) => !v)}
          className="px-3 py-2 rounded-xl text-xs font-semibold bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer shrink-0"
        >
          {expandAll ? "Comprimi tutto" : "Espandi tutto"}
        </button>
      </div>

      <LevelLegend maxDepth={maxDepth} />

      {filteredRoots.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-8">
          {search ? "Nessun promoter corrisponde alla ricerca." : "Nessun promoter nella rete."}
        </p>
      ) : (
        <div className="overflow-x-auto pb-4 space-y-6">
          {filteredRoots.map((root) => (
            <div key={root.agent_id} className="min-w-[600px] p-2">
              <div className="mb-2 px-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Radice di rete · {countNodes(root)} membri
                </span>
              </div>
              <TreeNodeRenderer
                node={root}
                onCopy={copyToClipboard}
                copiedId={copiedId}
                onNodeClick={(agentId, displayName) => setSelectedNode({ agentId, displayName })}
                startOpen
                forceOpen={expandAll || search.trim().length > 0}
              />
            </div>
          ))}
        </div>
      )}

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
