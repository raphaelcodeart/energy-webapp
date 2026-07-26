"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
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
  /** Center headerActions as a group instead of pushing it to the right with
      justify-between -- for pages with no headerSubtitle, justify-between
      would leave it looking stuck to the right against empty space rather
      than deliberately centered. Default false preserves the existing
      title/subtitle-on-left, actions-on-right layout. */
  centerHeaderActions?: boolean;
}

function LogoMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center rounded-xl bg-white p-1.5 shadow-sm shrink-0">
      <Image
        src="/logo.png"
        alt="Lial Energy"
        width={compact ? 32 : 40}
        height={compact ? 29 : 36}
        priority
        className="h-auto w-auto"
      />
    </div>
  );
}

/** Top-right icon cluster: theme toggle + avatar menu (classic dashboard corner). */
function UserMenu({ email, roleLabel }: { email?: string; roleLabel: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const initials = ((email || "?").split("@")[0] ?? "?")
    .split(/[._-]/)
    .map((p) => p[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-tr from-orange-600 to-amber-500 text-xs font-bold text-white shadow-md cursor-pointer"
        aria-label="Menu utente"
      >
        {initials}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-50 w-56 rounded-xl border border-white/10 light:border-slate-200 bg-slate-900 light:bg-white shadow-xl animate-scale-up overflow-hidden">
          <div className="px-4 py-3 border-b border-white/5 light:border-slate-100">
            <p className="truncate text-sm font-semibold text-white light:text-slate-900">{email}</p>
            <p className="truncate text-xs text-slate-400 light:text-slate-500">{roleLabel}</p>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-rose-400 light:text-rose-600 hover:bg-white/5 light:hover:bg-slate-50 transition cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Esci
          </button>
        </div>
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
  centerHeaderActions = false,
}: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

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
              className={`w-full flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-all cursor-pointer group ${
                active
                  ? "bg-gradient-to-r from-orange-600/15 to-amber-500/10 text-orange-300 light:text-orange-700 shadow-[inset_0_0_0_1px_rgba(139,92,246,0.25)]"
                  : "text-slate-400 light:text-slate-500 hover:bg-white/5 light:hover:bg-slate-900/5 hover:text-white light:hover:text-slate-900"
              }`}
            >
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${
                  active
                    ? "bg-orange-500/20 text-orange-400 light:bg-orange-100 light:text-orange-600"
                    : "bg-white/5 light:bg-slate-900/5 text-current opacity-80 group-hover:opacity-100 group-hover:bg-white/10 light:group-hover:bg-slate-900/10"
                }`}
              >
                {item.icon}
              </span>
              <span className="flex-1 text-left truncate">{item.label}</span>
              {active && <span className="h-1.5 w-1.5 rounded-full bg-orange-500 shrink-0" />}
            </button>
          );
        })}
      </nav>

      <div className="p-4 border-t border-white/5 light:border-slate-900/5 mt-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 light:text-slate-400">
          {roleLabel}
        </p>
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

      {/* Persistent top bar -- classic dashboard layout: page title left, icon
          cluster (theme toggle + avatar/logout menu) in the top-right corner. */}
      <header className="sticky top-0 z-40 flex items-center justify-between gap-4 border-b border-white/5 light:border-slate-900/5 bg-slate-950/80 light:bg-white/80 backdrop-blur-md px-4 sm:px-6 lg:px-8 lg:ml-64 h-16">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => setMobileOpen(true)}
            className="lg:hidden p-2 -ml-2 rounded-lg text-slate-300 light:text-slate-600 hover:bg-white/5 light:hover:bg-slate-900/5 cursor-pointer shrink-0"
            aria-label="Apri il menu"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div className="lg:hidden">
            <LogoMark compact />
          </div>
          {headerTitle && (
            <h1 className="hidden lg:block truncate text-base font-semibold text-white light:text-slate-900">
              {headerTitle}
            </h1>
          )}
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <ThemeToggle />
          <UserMenu email={email} roleLabel={roleLabel} />
        </div>
      </header>

      {/* Main content */}
      <div className="lg:pl-64">
        <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8 animate-slide-up">
          {(headerTitle || headerSubtitle || headerActions) && (
            <div
              className={`mb-8 flex flex-col gap-4 ${
                centerHeaderActions ? "" : "md:flex-row md:items-center md:justify-between"
              }`}
            >
              <div>
                <h1 className="lg:hidden text-2xl font-bold tracking-tight text-white light:text-slate-900 sm:text-3xl">
                  {headerTitle}
                </h1>
                {headerSubtitle && <div className="text-sm text-slate-400 light:text-slate-500 mt-1">{headerSubtitle}</div>}
              </div>
              {headerActions && <div className={centerHeaderActions ? "w-full" : "flex gap-3"}>{headerActions}</div>}
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}
