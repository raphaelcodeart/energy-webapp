"use client";

import { useState, type ReactNode } from "react";
import { LogoutButton } from "@/components/logout-button";
import { ThemeToggle } from "@/components/theme-toggle";

export interface NavItem {
  key: string;
  label: string;
  description?: string;
  icon: ReactNode;
}

interface AppShellProps {
  roleLabel: string;
  email?: string;
  navItems: NavItem[];
  activeKey: string;
  onNavigate: (key: string) => void;
  children: ReactNode;
  headerTitle?: string;
  headerSubtitle?: ReactNode;
  headerActions?: ReactNode;
}

function LogoMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="p-2 rounded-xl bg-gradient-to-tr from-violet-600 to-cyan-500 shadow-lg shadow-violet-500/20 shrink-0">
        <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      </div>
      {!compact && (
        <span className="text-lg font-bold tracking-tight text-white light:text-slate-900">
          LIAL <span className="text-violet-400 light:text-violet-600">ENERGY</span>
        </span>
      )}
    </div>
  );
}

export function AppShell({
  roleLabel,
  email,
  navItems,
  activeKey,
  onNavigate,
  children,
  headerTitle,
  headerSubtitle,
  headerActions,
}: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const initials = ((email || "?").split("@")[0] ?? "?")
    .split(/[._-]/)
    .map((p) => p[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const sidebarContent = (
    <div className="flex h-full flex-col">
      <div className="px-5 pt-6 pb-5">
        <LogoMark />
      </div>

      <nav className="flex-1 overflow-y-auto px-3 space-y-1">
        {navItems.map((item) => {
          const active = item.key === activeKey;
          return (
            <button
              key={item.key}
              onClick={() => {
                onNavigate(item.key);
                setMobileOpen(false);
              }}
              className={`w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all cursor-pointer group ${
                active
                  ? "bg-gradient-to-r from-violet-600/15 to-cyan-500/10 text-violet-300 light:text-violet-700 shadow-[inset_0_0_0_1px_rgba(139,92,246,0.25)]"
                  : "text-slate-400 light:text-slate-500 hover:bg-white/5 light:hover:bg-slate-900/5 hover:text-white light:hover:text-slate-900"
              }`}
            >
              <span className={`shrink-0 ${active ? "text-violet-400 light:text-violet-600" : "opacity-70 group-hover:opacity-100"}`}>
                {item.icon}
              </span>
              <span className="flex-1 text-left truncate">{item.label}</span>
              {active && <span className="h-1.5 w-1.5 rounded-full bg-violet-500 shrink-0" />}
            </button>
          );
        })}
      </nav>

      <div className="p-3 space-y-3 border-t border-white/5 light:border-slate-900/5 mt-2">
        <div className="flex items-center justify-between px-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 light:text-slate-400">
            Aspetto
          </span>
          <ThemeToggle />
        </div>

        <div className="flex items-center gap-2.5 rounded-xl bg-white/5 light:bg-slate-900/[0.03] p-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-tr from-violet-600 to-cyan-500 text-xs font-bold text-white">
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold text-white light:text-slate-900">{email}</p>
            <p className="truncate text-[10px] text-slate-400 light:text-slate-500">{roleLabel}</p>
          </div>
        </div>

        <LogoutButton className="w-full justify-center" />
      </div>
    </div>
  );

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar */}
      <aside className="hidden lg:block fixed inset-y-0 left-0 z-30 w-64 border-r border-white/5 light:border-slate-900/5 bg-slate-950/70 light:bg-white/70 backdrop-blur-xl">
        {sidebarContent}
      </aside>

      {/* Mobile sidebar (drawer) */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="relative z-10 w-72 h-full bg-slate-950 light:bg-white border-r border-white/5 light:border-slate-900/5 animate-scale-up">
            {sidebarContent}
          </aside>
        </div>
      )}

      {/* Mobile top bar */}
      <header className="lg:hidden sticky top-0 z-40 flex items-center justify-between border-b border-white/5 light:border-slate-900/5 bg-slate-950/80 light:bg-white/80 backdrop-blur-md px-4 h-16">
        <button
          onClick={() => setMobileOpen(true)}
          className="p-2 -ml-2 rounded-lg text-slate-300 light:text-slate-600 hover:bg-white/5 light:hover:bg-slate-900/5 cursor-pointer"
          aria-label="Apri il menu"
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <LogoMark compact />
        <ThemeToggle />
      </header>

      {/* Main content */}
      <div className="lg:pl-64">
        <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8 animate-slide-up">
          {(headerTitle || headerActions) && (
            <div className="mb-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
              <div>
                {headerTitle && (
                  <h1 className="text-2xl font-bold tracking-tight text-white light:text-slate-900 sm:text-3xl">
                    {headerTitle}
                  </h1>
                )}
                {headerSubtitle && <div className="text-sm text-slate-400 light:text-slate-500 mt-1">{headerSubtitle}</div>}
              </div>
              {headerActions && <div className="flex gap-3">{headerActions}</div>}
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}
