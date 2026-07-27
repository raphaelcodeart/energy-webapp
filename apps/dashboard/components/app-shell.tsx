"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ThemeToggle } from "@/components/theme-toggle";
import type { NotificationRead } from "@/lib/types";

export interface NavItem {
  key: string;
  label: string;
  description?: string;
  icon: ReactNode;
  /** Notification `type` values that should light up this nav item's unread
      dot -- e.g. Anagrafiche Promoter opts into PROMOTER_APPROVAL_REQUESTED.
      A nav item with no notificationTypes never shows a dot. */
  notificationTypes?: string[];
}

interface AppShellProps {
  roleLabel: string;
  email?: string;
  navItems: NavItem[];
  activeKey: string;
  onNavigate: (key: string, filter?: string) => void;
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

const NOTIFICATION_TYPE_LABELS: Record<string, string> = {
  CONTRACT_CREATED: "Nuovo contratto",
  TICKET_CREATED: "Nuovo ticket",
  PROMOTER_APPROVAL_REQUESTED: "Promoter da approvare",
  PROMOTER_APPROVED: "Promoter approvato",
  PROMOTER_REJECTED: "Promoter non approvato",
  COMMISSION_EARNED: "Nuova provvigione",
};

const NOTIFICATION_TYPE_ICONS: Record<string, ReactNode> = {
  CONTRACT_CREATED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
  ),
  TICKET_CREATED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
  ),
  PROMOTER_APPROVAL_REQUESTED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
  ),
  PROMOTER_APPROVED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
  ),
  PROMOTER_REJECTED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  ),
  COMMISSION_EARNED: (
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2" />
  ),
};

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "adesso";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min fa`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "ora" : "ore"} fa`;
  const days = Math.floor(hours / 24);
  return `${days} ${days === 1 ? "giorno" : "giorni"} fa`;
}

async function fetchNotifications(): Promise<NotificationRead[]> {
  const res = await fetch("/api/proxy/notifications/mine");
  if (!res.ok) return [];
  return res.json();
}

/** Bell icon + unread badge + dropdown -- polls every 25s so a new
    notification shows up without a manual refresh, without needing
    WebSockets for what is, for now, a low-volume internal tool. */
function NotificationBell({ onOpenNotification }: { onOpenNotification: (n: NotificationRead) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: notifications } = useQuery({
    queryKey: ["notifications", "mine"],
    queryFn: fetchNotifications,
    refetchInterval: 25000,
  });

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const list = notifications ?? [];
  const unreadCount = list.filter((n) => !n.is_read).length;

  async function handleClick(notification: NotificationRead) {
    setOpen(false);
    if (!notification.is_read) {
      await fetch(`/api/proxy/notifications/${notification.id}/read`, { method: "PATCH" });
      queryClient.invalidateQueries({ queryKey: ["notifications", "mine"] });
    }
    onOpenNotification(notification);
  }

  async function handleMarkAllRead() {
    await fetch("/api/proxy/notifications/mark-all-read", { method: "POST" });
    queryClient.invalidateQueries({ queryKey: ["notifications", "mine"] });
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-9 w-9 items-center justify-center rounded-full bg-white/5 light:bg-slate-900/5 hover:bg-white/10 light:hover:bg-slate-900/10 text-slate-300 light:text-slate-600 transition cursor-pointer"
        aria-label="Notifiche"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-50 w-80 max-h-[420px] overflow-y-auto rounded-xl border border-white/10 light:border-slate-200 bg-slate-900 light:bg-white shadow-xl animate-scale-up">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 light:border-slate-100 sticky top-0 bg-slate-900 light:bg-white">
            <p className="text-sm font-semibold text-white light:text-slate-900">Notifiche</p>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="text-[11px] text-orange-400 hover:text-orange-300 transition cursor-pointer"
              >
                Segna tutte come lette
              </button>
            )}
          </div>
          {list.length === 0 ? (
            <p className="text-xs text-slate-500 text-center py-8">Nessuna notifica.</p>
          ) : (
            <div className="divide-y divide-white/5 light:divide-slate-100">
              {list.map((n) => (
                <button
                  key={n.id}
                  onClick={() => handleClick(n)}
                  className={`w-full flex items-start gap-3 px-4 py-3 text-left transition cursor-pointer hover:bg-white/5 light:hover:bg-slate-50 ${
                    !n.is_read ? "bg-orange-500/5" : ""
                  }`}
                >
                  <span className="p-1.5 rounded-lg bg-orange-500/10 text-orange-400 shrink-0 mt-0.5">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      {NOTIFICATION_TYPE_ICONS[n.type] ?? <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01" />}
                    </svg>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-white light:text-slate-900 truncate">{n.title}</span>
                      {!n.is_read && <span className="w-1.5 h-1.5 rounded-full bg-orange-500 shrink-0" />}
                    </span>
                    {n.body && <span className="block text-[11px] text-slate-400 light:text-slate-500 mt-0.5 line-clamp-2">{n.body}</span>}
                    <span className="block text-[10px] text-slate-500 mt-1">
                      {NOTIFICATION_TYPE_LABELS[n.type] ?? n.type} · {timeAgo(n.created_at)}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
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

  const { data: notifications } = useQuery({
    queryKey: ["notifications", "mine"],
    queryFn: fetchNotifications,
    refetchInterval: 25000,
  });
  const unreadTypes = new Set((notifications ?? []).filter((n) => !n.is_read).map((n) => n.type));

  function handleOpenNotification(notification: NotificationRead) {
    const targetKey = navItems.find((item) => item.notificationTypes?.includes(notification.type))?.key;
    if (targetKey) onNavigate(targetKey);
  }

  const sidebarContent = (
    <div className="flex h-full flex-col">
      <div className="px-5 pt-6 pb-5">
        <LogoMark />
      </div>

      <nav className="flex-1 overflow-y-auto px-3 space-y-1">
        {navItems.map((item) => {
          const active = item.key === activeKey;
          const hasUnread = item.notificationTypes?.some((t) => unreadTypes.has(t)) ?? false;
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
                className={`relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${
                  active
                    ? "bg-orange-500/20 text-orange-400 light:bg-orange-100 light:text-orange-600"
                    : "bg-white/5 light:bg-slate-900/5 text-current opacity-80 group-hover:opacity-100 group-hover:bg-white/10 light:group-hover:bg-slate-900/10"
                }`}
              >
                {item.icon}
                {hasUnread && (
                  <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-rose-500 border-2 border-slate-950 light:border-white" />
                )}
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
          <NotificationBell onOpenNotification={handleOpenNotification} />
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
