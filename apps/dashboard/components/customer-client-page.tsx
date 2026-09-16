"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { AccountingPanel } from "@/components/accounting-panel";
import { AppShell, type NavItem } from "@/components/app-shell";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { ContractRequestsList, type WizardTarget } from "@/components/contract-requests-list";
import { DashboardWalletStats } from "@/components/dashboard-wallet-stats";
import { WelcomeBonusCard } from "@/components/welcome-bonus-card";
import { CustomerOrdersPanel } from "@/components/customer-orders-panel";
import { CustomerProductsPanel } from "@/components/customer-products-panel";
import { CustomerPromoterApplicationCard } from "@/components/customer-promoter-application-card";
import { FriendReferralsPanel } from "@/components/friend-referrals-panel";
import { DocumentationFeed } from "@/components/documentation-feed";
import { SectionBanner } from "@/components/section-banner";
import { SupportTicketsPanel } from "@/components/support-tickets-panel";
import { WalletPanel } from "@/components/wallet-panel";
import { InvoiceRedemptionPanel } from "@/components/invoice-redemption-panel";
import type { ContractRead, CustomerRead } from "@/lib/types";

/** Shared "you just came back from Stripe Checkout" banner -- used by both
    the "I miei Ordini" and "Riscatta Cashback" tabs (see the useEffect in
    CustomerClientPage that reads ?payment=success|cancelled&tab=... and sets
    paymentBanner), just with different body copy for what's actually being
    confirmed. */
function PaymentReturnBanner({
  state, onDismiss, successBody, cancelledBody,
}: {
  state: "success" | "cancelled" | null;
  onDismiss: () => void;
  successBody: string;
  cancelledBody: string;
}) {
  if (state === null) return null;
  const isSuccess = state === "success";
  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-xl border text-sm animate-fade-in ${
        isSuccess
          ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
          : "bg-amber-500/10 border-amber-500/20 text-amber-400"
      }`}
    >
      <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        {isSuccess ? (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        )}
      </svg>
      <div className="flex-1">
        <p className="font-semibold">{isSuccess ? "Pagamento completato con successo!" : "Pagamento non completato"}</p>
        <p className={`text-xs mt-0.5 ${isSuccess ? "text-emerald-400/80" : "text-amber-400/80"}`}>
          {isSuccess ? successBody : cancelledBody}
        </p>
      </div>
      <button
        onClick={onDismiss}
        className={`p-1 rounded-lg cursor-pointer shrink-0 ${isSuccess ? "hover:bg-emerald-500/10" : "hover:bg-amber-500/10"}`}
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

async function fetchMyCustomerRecord(): Promise<CustomerRead | null> {
  const res = await fetch("/api/proxy/customers/me");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Impossibile caricare la tua anagrafica.");
  return res.json();
}

interface CustomerClientPageProps {
  /** Server-fetched at page load. No longer rendered directly: since
      Session 52 contracts are shown inside their pratiche
      (contract-requests-list.tsx), which load themselves. */
  contracts: ContractRead[];
  email?: string;
  /** Needed to build the customer's own "Invita un amico" link, which
      carries ?org= exactly like a promoter's referral link does. */
  organizationId?: string;
}

const NAV_ITEMS: NavItem[] = [
  {
    key: "lial-contracts",
    // Was "Contratti Lial Energy" -- accurate back when this tab was just
    // the contract-activation list, but since Session 33's redesign it's
    // the actual dashboard home (wallet stats, quick-access shortcuts,
    // THEN the contracts list), so the label and icon were updated to
    // match what a customer actually lands on -- "Home" reads clearer to
    // a non-technical user on a mobile tab bar than "Dashboard" would.
    label: "Home",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l9-9 9 9M5 10v10a1 1 0 001 1h3a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1h3a1 1 0 001-1V10" />
      </svg>
    ),
  },
  {
    key: "products",
    label: "Shop",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    key: "orders",
    label: "I miei Ordini",
    notificationTypes: ["ORDER_PAID"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 2l1 4H4a1 1 0 00-1 1v1a1 1 0 001 1h16a1 1 0 001-1V7a1 1 0 00-1-1h-6l1-4M5 9v9a2 2 0 002 2h10a2 2 0 002-2V9M10 13h4" />
      </svg>
    ),
  },
  {
    key: "contracts",
    label: "I miei Contratti",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    key: "support",
    label: "Supporto & Assistenza",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
  {
    key: "friend-referrals",
    label: "Invita un amico",
    notificationTypes: ["FRIEND_REFERRAL_ACTIVATED", "FRIEND_REFERRAL_REWARD_HANDLED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
  },
  {
    key: "promoter-application",
    label: "Lavora con noi",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-8a4 4 0 11-8 0 4 4 0 018 0zm6 3a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
  },
  {
    key: "documentation",
    label: "Documentazione",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    key: "wallet",
    label: "Wallet",
    notificationTypes: ["CASHBACK_RECEIVED", "WALLET_TRANSFER_RECEIVED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
      </svg>
    ),
  },
  {
    key: "cashback",
    label: "Riscatta Cashback",
    notificationTypes: ["INVOICE_REDEMPTION_VERIFIED", "INVOICE_REDEMPTION_REJECTED"],
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 14l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    key: "accounting",
    label: "Contabilità",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m-6 4h6m-6 4h4M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z" />
      </svg>
    ),
  },
];

/** Quick-access shortcuts on the dashboard home -- one click into the
    sections a customer actually returns to often, instead of only
    reachable via the sidebar. Same pattern as the promoter home and the
    admin Panoramica. */
const HOME_QUICK_LINKS: { key: string; label: string; description: string; icon: React.ReactNode }[] = [
  {
    key: "contracts",
    label: "Contratti",
    description: "Attiva luce e gas",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    key: "products",
    label: "Shop",
    description: "Acquista prodotti",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    key: "orders",
    label: "I miei Ordini",
    description: "Dettaglio dei tuoi acquisti",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 2l1 4H4a1 1 0 00-1 1v1a1 1 0 001 1h16a1 1 0 001-1V7a1 1 0 00-1-1h-6l1-4M5 9v9a2 2 0 002 2h10a2 2 0 002-2V9M10 13h4" />
      </svg>
    ),
  },
  {
    key: "cashback",
    label: "Riscatta Cashback",
    description: "Da fattura a LialCash",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 14l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    key: "wallet",
    label: "Wallet",
    description: "Saldo e movimenti",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M21 12a2 2 0 00-2-2H7a2 2 0 00-2 2m16 0v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6m16 0V9a2 2 0 00-2-2H5a2 2 0 00-2 2v3m16 0h-4a1 1 0 00-1 1v0a1 1 0 001 1h4" />
      </svg>
    ),
  },
  {
    key: "accounting",
    label: "Contabilità",
    description: "Tutte le tue transazioni",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M9 7h6m-6 4h6m-6 4h4M5 3h14a2 2 0 012 2v14a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z" />
      </svg>
    ),
  },
  {
    key: "support",
    label: "Supporto",
    description: "Hai bisogno di aiuto?",
    icon: (
      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
      </svg>
    ),
  },
];

export function CustomerClientPage({ email, organizationId }: CustomerClientPageProps) {
  // "lial-contracts" is the customer's home -- matches the Shop's old default
  // landing tab, back when Lial Energy contracts were its first category
  // (see NAV_ITEMS ordering below).
  const [activeTab, setActiveTab] = useState<"lial-contracts" | "contracts" | "products" | "orders" | "support" | "promoter-application" | "friend-referrals" | "documentation" | "wallet" | "cashback" | "accounting">("lial-contracts");
  // "Attiva nuovo contratto" / "Riprendi" / "Paga": the pratica wizard,
  // opened over whichever tab the customer is on.
  const [wizard, setWizard] = useState<WizardTarget | "new" | null>(null);
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [paymentBanner, setPaymentBanner] = useState<"success" | "cancelled" | null>(null);

  // Landing back here from Stripe Checkout (success_url/cancel_url set by
  // customer-orders-panel.tsx's "Paga con carta" or invoice-redemption-
  // panel.tsx's "Paga con carta" for a cashback redemption fee) -- switch to
  // the right tab, show a banner, and refetch so the order/redemption's
  // status (still AWAITING_PAYMENT/PAYMENT_PENDING until the webhook lands,
  // usually within a couple of seconds) updates without a manual reload. The
  // query params are stripped right after reading them so a page refresh
  // doesn't re-trigger the banner.
  const VALID_TABS = [
    "lial-contracts", "activate-contract", "contracts", "products", "orders", "support",
    "promoter-application", "friend-referrals", "documentation", "wallet", "cashback", "accounting",
  ] as const;

  useEffect(() => {
    const payment = searchParams.get("payment");
    const tab = searchParams.get("tab");
    const isValidTab = (VALID_TABS as readonly string[]).includes(tab ?? "");
    if (!payment && !isValidTab) return;

    // A plain deep-link from an email ("Vai al wallet" etc, ?tab=wallet, no
    // ?payment=) just switches tab -- only a Stripe Checkout return
    // (?payment=success|cancelled, always paired with tab=orders|cashback)
    // also shows the payment banner and refetches.
    // "activate-contract" was its own tab until Session 52; old links and
    // emails still point at it.
    if (tab === "activate-contract") setActiveTab("contracts");
    else if (isValidTab) setActiveTab(tab as typeof activeTab);
    const queryKey =
      tab === "cashback"
        ? ["invoice-redemptions", "mine"]
        : tab === "contracts"
          ? ["contract-requests"]
          : ["customer", "orders"];
    if (payment === "success" || payment === "cancelled") {
      setPaymentBanner(payment);
      queryClient.invalidateQueries({ queryKey });
    }
    router.replace("/customer", { scroll: false });

    if (payment === "success") {
      // The webhook is usually near-instant but not guaranteed to have
      // landed by the time Stripe redirects back -- one extra refetch a
      // couple seconds later catches the status flipping to PAID/CREDITED
      // without requiring the customer to refresh manually.
      const timer = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey });
      }, 3000);
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const { data: myCustomer } = useQuery({
    queryKey: ["customer", "me", "record"],
    queryFn: fetchMyCustomerRecord,
  });

  return (
    <AppShell
      roleLabel="Area Cliente"
      email={email}
      navItems={NAV_ITEMS}
      activeKey={activeTab}
      onNavigate={(key) => setActiveTab(key as typeof activeTab)}
      headerTitle="La mia Area Cliente"
      // Not on Contabilità (Session 54): the page has its own heading, and the
      // space goes to the totals.
      headerSubtitle={
        activeTab === "accounting"
          ? undefined
          : "Visualizza lo stato dei tuoi contratti di fornitura luce/gas e richiedi assistenza."
      }
    >
      {activeTab === "contracts" && (
        <div className="space-y-6">
          <SectionBanner image="energy" alt="I miei Contratti" />
          <PaymentReturnBanner
            state={paymentBanner}
            onDismiss={() => setPaymentBanner(null)}
            successBody="La pratica si aggiorna a “Pagato” appena Stripe conferma, di solito in pochi secondi. Ogni contratto si attiva quando i suoi documenti sono approvati."
            cancelledBody="Nessun addebito. Puoi pagare quando vuoi con il pulsante “Paga” della pratica."
          />
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl border border-orange-500/25 bg-gradient-to-br from-orange-500/10 to-transparent">
            <div>
              <h3 className="text-base font-bold text-white light:text-slate-900">Le tue pratiche di attivazione</h3>
              <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
                Una pratica può contenere uno o più punti di fornitura (POD luce, PDR gas): ogni punto è un contratto a sé,
                con il suo pacchetto. Dati, documenti e pagamento li gestisci una volta sola.
              </p>
            </div>
            <button
              onClick={() => setWizard("new")}
              className="shrink-0 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 text-white text-sm font-bold shadow-lg shadow-orange-500/20 transition cursor-pointer"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
              </svg>
              Attiva nuovo contratto
            </button>
          </div>
          <ContractRequestsList mode="customer" onOpenWizard={(target) => setWizard(target)} />
          <div className="pt-2">
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-3">Scopri i pacchetti</p>
            <CustomerProductsPanel visibleCategories={["INTERNAL"]} accountEmail={email} />
          </div>
        </div>
      )}

      {activeTab === "lial-contracts" && (
        <div className="space-y-6">
          <SectionBanner image="energy" alt="Area Cliente" compact>
            <div>
              <p className="text-[11px] font-semibold text-orange-300 uppercase tracking-wider">Bentornato</p>
              <h2 className="text-lg sm:text-xl font-bold text-white truncate max-w-[70vw] sm:max-w-none">{email}</h2>
            </div>
          </SectionBanner>

          <WelcomeBonusCard />


          <DashboardWalletStats />

          <div>
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2.5">Accesso rapido</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {HOME_QUICK_LINKS.map((link) => (
                <button
                  key={link.key}
                  onClick={() => setActiveTab(link.key as typeof activeTab)}
                  className="group flex flex-col items-start gap-3 p-4 rounded-2xl border border-white/5 light:border-slate-200 bg-gradient-to-br from-slate-900/60 to-slate-900/20 light:from-white light:to-slate-50 hover:border-orange-500/40 hover:shadow-lg hover:shadow-orange-500/10 transition-all duration-200 cursor-pointer text-left"
                >
                  <span className="p-2.5 rounded-xl bg-orange-500/10 text-orange-400 group-hover:bg-orange-500 group-hover:text-white transition-colors">
                    {link.icon}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-white light:text-slate-900 truncate">
                      {link.label}
                    </span>
                    <span className="block text-[11px] text-slate-500 truncate">{link.description}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          <CustomerPromoterApplicationCard hideWhenActive />
          <CustomerProductsPanel visibleCategories={["INTERNAL"]} accountEmail={email} />
        </div>
      )}

      {activeTab === "products" && (
        <div className="space-y-6">
          <SectionBanner image="products" alt="Shop" />
          <CustomerProductsPanel visibleCategories={["PARTNER", "DROPSHIPPING"]} showImportedTab />
        </div>
      )}

      {activeTab === "orders" && (
        <div className="space-y-6">
          <SectionBanner image="products" alt="I miei Ordini" />
          <PaymentReturnBanner
            state={paymentBanner}
            onDismiss={() => setPaymentBanner(null)}
            successBody="L'ordine si aggiorna automaticamente a “Pagato” non appena Stripe conferma -- di solito pochi secondi."
            cancelledBody="Puoi riprovare quando vuoi dal tuo ordine qui sotto."
          />
          <CustomerOrdersPanel />
        </div>
      )}

      {activeTab === "support" && (
        <div className="space-y-6">
          <SectionBanner image="support" alt="Supporto & Assistenza" />
          <SupportTicketsPanel
            title="Supporto & Assistenza"
            subtitle="Apri un ticket per problemi tecnici, fatturazione o domande sul tuo contratto: un operatore ti risponderà qui."
          />
        </div>
      )}

      {activeTab === "friend-referrals" && (
        <FriendReferralsPanel organizationId={organizationId} />
      )}

      {activeTab === "promoter-application" && (
        <div className="space-y-6">
          <CustomerPromoterApplicationCard />
        </div>
      )}

      {activeTab === "documentation" && (
        <div className="space-y-6">
          <SectionBanner image="documentation" alt="Documentazione" />
          <DocumentationFeed />
        </div>
      )}

      {activeTab === "wallet" && (
        <div className="space-y-6">
          <SectionBanner image="wallets" alt="Wallet" />
          <WalletPanel />
        </div>
      )}

      {activeTab === "cashback" && (
        <div className="space-y-6">
          <SectionBanner image="wallets" alt="Riscatta Cashback" />
          <PaymentReturnBanner
            state={paymentBanner}
            onDismiss={() => setPaymentBanner(null)}
            successBody="La richiesta si aggiorna automaticamente ad “Accreditata” non appena Stripe conferma -- di solito pochi secondi."
            cancelledBody="Puoi riprovare quando vuoi dalla tua richiesta qui sotto."
          />
          <InvoiceRedemptionPanel />
        </div>
      )}

      {activeTab === "accounting" && (
        <AccountingPanel onOpenTab={(tab) => setActiveTab(tab as typeof activeTab)} />
      )}
      {wizard && (
        <ContractRequestWizard
          requestId={wizard === "new" ? undefined : wizard.requestId}
          initialStep={wizard === "new" ? undefined : wizard.step}
          customerKind={myCustomer?.kind ?? null}
          accountEmail={email}
          holder={{ firstName: myCustomer?.first_name, lastName: myCustomer?.last_name, pec: myCustomer?.pec }}
          onClose={() => setWizard(null)}
        />
      )}
    </AppShell>
  );
}
