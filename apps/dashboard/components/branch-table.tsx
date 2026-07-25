"use client";

import { flexRender, getCoreRowModel, useReactTable, createColumnHelper } from "@tanstack/react-table";
import type { BranchMemberRead } from "@/lib/types";

const columnHelper = createColumnHelper<BranchMemberRead>();

const columns = [
  columnHelper.accessor("agent_id", {
    header: "Agente",
    cell: (info) => <span className="font-mono text-xs">{info.getValue()}</span>,
  }),
  columnHelper.accessor("depth", {
    header: "Profondità nel ramo",
  }),
];

export function BranchTable({ members }: { members: BranchMemberRead[] }) {
  const table = useReactTable({ data: members, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        {table.getHeaderGroups().map((headerGroup) => (
          <tr key={headerGroup.id} className="border-b border-slate-200 text-left dark:border-slate-800">
            {headerGroup.headers.map((header) => (
              <th key={header.id} className="py-2 pr-4">
                {flexRender(header.column.columnDef.header, header.getContext())}
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody>
        {table.getRowModel().rows.map((row) => (
          <tr key={row.id} className="border-b border-slate-100 dark:border-slate-900">
            {row.getVisibleCells().map((cell) => (
              <td key={cell.id} className="py-2 pr-4">
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
