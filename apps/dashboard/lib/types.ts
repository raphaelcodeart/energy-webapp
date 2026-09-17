// Mirrors the Pydantic response schemas in apps/api/app/domains/*/schemas.py.
// Kept hand-written for this vertical slice; generating from the OpenAPI schema
// (packages/api-client) is tracked as Phase F follow-up work.

export type ContractRead = {
  id: string;
  customer_id: string;
  supply_point_id: string;
  /** Null only while the contract is a draft point of a pratica whose
      package has not been chosen yet (Session 52). */
  product_version_id: string | null;
  /** The pratica this contract was filled in and paid with. */
  contract_request_id?: string | null;
  status: string;
  notes: string | null;
  created_at: string;
  activated_at: string | null;
  expires_at: string | null;
  product_name: string | null;
  supply_point_label: string | null;
  pod_code?: string | null;
  pdr_code?: string | null;
  /** ELECTRICITY / GAS -- of the supply point. */
  energy_type?: string | null;
  iban: string | null;
  email: string | null;
  /** Intestatario as typed in the activation wizard (Session 49). Null on
      older and staff-created contracts. */
  holder_first_name: string | null;
  holder_last_name: string | null;
  pec: string | null;

  // --- Chi lo ha costruito (Session 38) ---
  /** CUSTOMER / PROMOTER / ADMIN. Null on contracts created before this
      existed -- the creator is still in the status history. */
  created_by_role: string | null;
  /** Set ONLY when a promoter completed the contract in place of the
      customer. Null means the customer signed up themselves -- which is why
      the admin screen can say which of the two happened instead of guessing
      from whoever earns the commission. */
  activated_by_promoter_id: string | null;
  activated_by_promoter_name: string | null;
  /** The promoter who originally brought this customer in -- a different
      person whenever somebody else assisted them. */
  first_referrer_agent_id: string | null;
  first_referrer_name: string | null;

  // --- Economia congelata alla creazione ---
  customer_kind: string | null;
  net_amount_cents: number | null;
  /** Percentage points (22.0), not a fraction. 0 for a private customer. */
  vat_rate: number | null;
  vat_amount_cents: number | null;
  gross_amount_cents: number | null;

  // --- Pagamento ---
  payment_plan: string | null;
  payment_method: string | null;
  paid_at: string | null;
  /** An administrator stopped Stripe charging this contract every month. */
  billing_stopped_at?: string | null;
  terms_accepted_at: string | null;
  terms_version: string | null;
};

// --- Pratica di attivazione (Session 52) ---------------------------------

/** One row of every pratiche list. Every count is derived server-side from
    the contracts, never stored twice. */
export type ContractRequestSummaryRead = {
  id: string;
  /** First 8 characters of the id, upper case -- how a pratica is named aloud. */
  code: string;
  customer_id: string;
  customer_name: string | null;
  customer_kind: string | null;
  /** DRAFT / SUBMITTED / CANCELLED */
  status: string;
  created_at: string;
  submitted_at: string | null;
  updated_at: string | null;
  created_by_role: string | null;
  activated_by_promoter_id: string | null;
  activated_by_promoter_name: string | null;
  holder_name: string | null;
  points_total: number;
  points_by_status: Record<string, number>;
  points_active: number;
  points_to_review: number;
  points_documents_pending: number;
  points_without_package: number;
  points_paid: number;
  points_payable: number;
  total_gross_cents: number;
  payment_plans: string[];
  instalments_failed: number;
};

export type ContractRequestPointRead = ContractRead & {
  /** 1-based place of the POD in the pratica. */
  position: number;
  meter_number: string | null;
  street: string | null;
  city: string | null;
  province: string | null;
  postal_code: string | null;
  product_id: string | null;
  documents_missing: number;
  documents_rejected: number;
  instalments_total: number | null;
  instalments_paid: number;
  instalments_failed: number;
  /** Stripe is still charging this contract every month. */
  billing_active: boolean;
};

export type ContractRequestCheckoutRead = {
  id: string;
  created_at: string;
  payment_plan: string;
  total_cents: number;
  instalment_cents: number;
  contracts: number;
  completed_at: string | null;
  stripe_checkout_session_id: string;
  stripe_subscription_id: string | null;
  outcome: string | null;
};

export type ContractRequestDetailRead = ContractRequestSummaryRead & {
  /** The supply address every POD of the pratica starts from. */
  street: string | null;
  city: string | null;
  province: string | null;
  postal_code: string | null;
  holder_first_name: string | null;
  holder_last_name: string | null;
  email: string | null;
  pec: string | null;
  iban: string | null;
  points: ContractRequestPointRead[];
  /** Staff only. */
  checkouts: ContractRequestCheckoutRead[];
};

export type ContractRequestPaymentOptionRead = {
  key: string;
  label: string;
  description: string;
  instalments: number;
  instalment_cents: number;
  total_cents: number;
  rounding_difference_cents: number;
  available: boolean;
  unavailable_reason: string | null;
};

export type ContractRequestPaymentOptionsRead = {
  contract_request_id: string;
  card_available: boolean;
  lines: { contract_id: string; label: string; gross_cents: number }[];
  total_gross_cents: number;
  options: ContractRequestPaymentOptionRead[];
  points_paid: number;
  cashback_total_cents: number;
  /** On an instalment plan: a slice per instalment, or all at the first. */
  cashback_mode: "PER_INSTALMENT" | "UPFRONT";
};

export type ContractStatusHistoryRead = {
  id: string;
  from_status: string | null;
  to_status: string;
  actor_user_id: string;
  actor_name: string;
  reason: string | null;
  notes: string | null;
  created_at: string;
};

export type CommissionMovementRead = {
  id: string;
  agent_id: string;
  contract_id: string;
  movement_type: string;
  amount_cents: number;
  currency: string;
  status: string;
  effective_date: string;
};

export type NotificationRead = {
  id: string;
  type: string;
  entity_type: string;
  entity_id: string;
  title: string;
  body: string | null;
  is_read: boolean;
  created_at: string;
};

export type CommissionMovementDetailRead = {
  id: string;
  contract_id: string;
  customer_id: string;
  customer_name: string;
  product_name: string;
  value_cents: number;
  agent_id: string;
  agent_name: string;
  agent_promoter_code: string;
  agent_current_rank_code: string | null;
  producer_agent_id: string;
  producer_name: string;
  depth_from_producer: number | null;
  movement_type: string;
  rank_at_calculation: string | null;
  base_amount_cents: number | null;
  already_distributed_cents: number | null;
  entrepreneurial_difference_cents: number | null;
  amount_cents: number;
  explanation: string | null;
  status: string;
  effective_date: string;
  paid_date: string | null;
};

export type CommissionLevelTotalsRead = {
  depth: number;
  contracts: number;
  value_cents: number;
  commission_cents: number;
};

export type BranchMemberRead = {
  agent_id: string;
  depth: number;
  display_name: string;
  promoter_code: string;
  status: string;
  rank_code: string | null;
  parent_agent_id: string | null;
  /** The person's ACCOUNT is frozen -- distinct from `status` (their agent
      lifecycle). Only ever true for admin-tier viewers: the server prunes
      frozen members and their whole subtree for everyone else. */
  is_frozen?: boolean;
};

export type AgentProfileRead = {
  id: string;
  organization_id: string;
  user_id: string | null;
  display_name: string;
  promoter_code: string;
  status: string;
  photo_url: string | null;
  current_rank_id: string | null;
  rank_code: string | null;
  rejection_reason: string | null;
  is_blacklisted: boolean;
  collaboration_accepted_at: string | null;
  /** {key: {version, accepted_at}} -- which documents this promoter
      accepted and at which wording. Empty for anyone who signed up before
      multi-document acceptance existed. */
  collaboration_accepted_documents?: Record<string, { version: string; accepted_at: string }>;
};

export type SimulationStepRead = {
  beneficiary_agent_id: string;
  rank_code: string;
  gross_amount_cents: number;
  movement_type: string;
  explanation: string;
};

export type RankRead = {
  id: string;
  code: string;
  name: string;
  level: number;
  personal_token_cents: number;
};

export type RankEvaluationChangeRead = {
  agent_id: string;
  display_name: string;
  previous_rank_code: string | null;
  new_rank_code: string;
  direction: "PROMOTED" | "DEMOTED";
};

export type CustomerRead = {
  id: string;
  organization_id: string;
  user_id: string | null;
  kind: string;
  fiscal_code: string | null;
  vat_number: string | null;
  email: string;
  phone: string | null;
  pec: string | null;
  photo_url: string | null;
  display_name: string;
  /** Null for a company/condominium with no person's profile. */
  first_name: string | null;
  last_name: string | null;
  created_at: string;
  email_verified: boolean | null;
  privacy_accepted: boolean | null;
  user_status: "ACTIVE" | "FROZEN" | null;
};

export type AddressRead = {
  id: string;
  kind: string;
  street: string;
  city: string;
  province: string;
  postal_code: string;
  country: string;
};

export type SupplyPointRead = {
  id: string;
  label: string | null;
  energy_type: string;
  pod_code: string | null;
  pdr_code: string | null;
  meter_number: string | null;
  supply_address_id: string;
};

export type CustomerDetailRead = CustomerRead & {
  addresses: AddressRead[];
  supply_points: SupplyPointRead[];
  current_promoter_agent_id: string | null;
  current_promoter_name: string | null;
};

export type AgentListItemRead = {
  id: string;
  display_name: string;
  first_name: string | null;
  last_name: string | null;
  promoter_code: string;
  status: string;
  photo_url: string | null;
  current_rank_id: string | null;
  rank_code: string | null;
  direct_parent_agent_id: string | null;
  joined_at: string;
  rejection_reason: string | null;
  email: string | null;
  is_blacklisted: boolean;
  user_id: string | null;
  collaboration_accepted_at: string | null;
  /** {key: {version, accepted_at}} -- which documents this promoter
      accepted and at which wording. Empty for anyone who signed up before
      multi-document acceptance existed. */
  collaboration_accepted_documents?: Record<string, { version: string; accepted_at: string }>;
  email_verified: boolean;
  privacy_accepted: boolean;
  user_status: "ACTIVE" | "FROZEN" | null;
};

export type RootPromoterCreateResponse = {
  agent_id: string;
  display_name: string;
  promoter_code: string;
  personal_link: string;
  email: string;
  temporary_password: string;
};

export type DocumentationPostRead = {
  id: string;
  title: string;
  body: string | null;
  audience: "CUSTOMER" | "PROMOTER" | "BOTH";
  status: "PUBLISHED" | "ARCHIVED";
  image_url: string | null;
  pdf_url: string | null;
  pdf_filename: string | null;
  video_url: string | null;
  created_at: string;
};

export type ProductVersionRead = {
  id: string;
  version_label: string;
  name: string;
  description: string;
  image_url: string | null;
  base_price_cents: number;
  initial_fee_cents: number;
  recurring_fee_cents: number;
  billing_period: string;
  vat_percentage: number | null;
  contract_duration_months: number | null;
  commission_tokens: Record<string, number>;
  credit_discount_percentage: number;
  cashback_enabled: boolean;
  /** 0-100: share of a paid CONTRACT's gross (VAT included) credited back as
      LialCash, automatically and with no surcharge. INTERNAL products only;
      0 means a contract generates no LialCash at all. */
  contract_cashback_percentage: number;
  /** One-off bonus to the promoter who originally brought the customer in.
      Configured here rather than keyed off a price in code. */
  first_referrer_bonus_enabled: boolean;
  first_referrer_bonus_cents: number;
  /** NO_CASHBACK / STANDARD / AUTOMATIC_INTERNAL_SERVICE -- derived server-side
      from the fields above plus the product's category, never stored. */
  cashback_mode: string;
  /** How many canoni one contract is made of (12 for a monthly price on a
      12-month contract) and the whole contract's price before VAT --
      computed server-side (catalog/pricing.py::contract_net_amount_cents). */
  contract_billing_periods: number;
  contract_net_amount_cents: number;
  valid_from: string;
  valid_to: string | null;
  status: string;
};

export type ProductRead = {
  id: string;
  organization_id: string;
  code: string;
  product_type: string;
  energy_type: string | null;
  customer_type: string;
  status: string;
  category: "INTERNAL" | "DROPSHIPPING" | "PARTNER";
};

export type ProductWithVersionsRead = ProductRead & {
  versions: ProductVersionRead[];
};

export type ProductCatalogRead = ProductRead & {
  current_version: ProductVersionRead | null;
};

export type ContractTotals = {
  total: number;
  active: number;
  pending_approval: number;
  rejected: number;
  cancelled: number;
  suspended: number;
  expired: number;
};

export type CommissionTotals = {
  accrued_cents: number;
  payable_cents: number;
  paid_cents: number;
  reversed_cents: number;
};

export type DashboardSummary = {
  contracts: ContractTotals;
  commissions: CommissionTotals;
  active_promoters: number;
  active_customers: number;
  period_new_contracts: number;
  period_new_commissions_cents: number;
  generated_at: string;
};

export type AttentionItem = {
  contract_id: string;
  customer_id: string;
  status: string;
  days_in_status: number;
  reason: string;
};

export type RecentActivityItem = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  reason: string | null;
  created_at: string;
};

export type TimeseriesPoint = {
  period: string;
  value: number;
};

export type PromoterCodeRead = {
  id: string;
  code: string;
  personal_link: string;
  status: string;
  promoter_display_name: string | null;
};

export type BranchAgentSummaryRead = {
  agent_id: string;
  depth: number;
  display_name: string;
  promoter_code: string;
  status: string;
  rank_code: string | null;
  contracts_total: number;
  contracts_by_status: Record<string, number>;
  contracts_problem: number;
  contracts_in_progress: number;
  contracts_processed: number;
  commission_cents: number;
};

export type BranchSummaryTotals = {
  contracts: number;
  commission_cents: number;
  contracts_by_status: Record<string, number>;
  contracts_closed: number;
  contracts_rejected: number;
  contracts_pending: number;
  contracts_in_progress: number;
  levels_below: number;
  people_total: number;
};

export type BranchSummaryRead = {
  agents: BranchAgentSummaryRead[];
  totals: BranchSummaryTotals;
};

export type RankProgressRead = {
  current_rank_code: string | null;
  current_rank_name: string | null;
  next_rank_code: string | null;
  next_rank_name: string | null;
  is_max_rank: boolean;
  personal_volume_cents: number;
  personal_volume_threshold_cents: number;
  group_volume_cents: number;
  group_volume_threshold_cents: number;
};

export type OrganizationNetworkLevelsRead = {
  people_total: number;
  levels_total: number;
  people_by_level: Record<string, number>;
};

export type BranchContractRead = {
  contract_id: string;
  status: string;
  customer_id: string;
  customer_name: string;
  customer_email: string | null;
  customer_phone: string | null;
  product_name: string;
  value_cents: number;
  supply_point_label: string | null;
  expires_at: string | null;
  producer_agent_id: string;
  producer_name: string;
  commission_cents: number;
  my_commission_cents: number | null;
  is_problem: boolean;
  admin_note: string | null;
};

export type TicketMessageRead = {
  id: string;
  ticket_id: string;
  author_user_id: string;
  author_role: string;
  author_name: string | null;
  body: string;
  created_at: string;
};

export type TicketRead = {
  id: string;
  organization_id: string;
  opened_by_user_id: string;
  opened_by_role: string;
  opened_by_name: string | null;
  subject: string;
  category: string;
  status: string;
  contract_id: string | null;
  created_at: string;
  message_count: number;
  last_message_at: string | null;
};

export type TicketDetailRead = TicketRead & {
  messages: TicketMessageRead[];
};

export type WalletRead = {
  id: string;
  user_id: string;
  address: string;
  balance_cents: number;
  currency: string;
  can_transfer: boolean;
  created_at: string;
};

export type WalletAdminListItemRead = WalletRead & {
  owner_display_name: string;
  owner_email: string;
  owner_roles: string[];
};

export type WalletTransactionRead = {
  id: string;
  from_wallet_id: string | null;
  from_address: string | null;
  from_display_name: string | null;
  to_wallet_id: string | null;
  to_address: string | null;
  to_display_name: string | null;
  amount_cents: number;
  currency: string;
  type: string;
  source: string | null;
  reference_contract_id: string | null;
  reference_invoice_redemption_id: string | null;
  reference_order_id: string | null;
  reference_imported_order_id: string | null;
  reverses_transaction_id: string | null;
  note: string | null;
  actor_user_id: string | null;
  created_at: string;
};

export type OrganizationSettingsRead = {
  bank_iban: string | null;
  bank_account_holder: string | null;
  bank_transfer_instructions: string | null;
  /** PER_INSTALMENT (default) / UPFRONT -- Session 59. */
  contract_instalment_cashback_mode: "PER_INSTALMENT" | "UPFRONT" | null;
};

export type PaymentSettingsRead = {
  stripe_publishable_key: string | null;
  stripe_secret_key_configured: boolean;
  stripe_secret_key_last4: string | null;
  stripe_webhook_secret_configured: boolean;
};

export type PartnerRead = {
  id: string;
  name: string;
  logo_url: string | null;
  is_active: boolean;
};

export type OrderRead = {
  id: string;
  customer_user_id: string;
  customer_display_name: string;
  product_version_id: string;
  product_name: string;
  product_image_url: string | null;
  created_by_user_id: string;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  cashback_requested: boolean;
  cashback_surcharge_cents: number;
  cashback_credited_at: string | null;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

export type OrderQuoteRead = {
  product_version_id: string;
  product_name: string;
  amount_cents: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_available: boolean;
  card_available: boolean;
  cashback_available: boolean;
  cashback_percentage: number;
};

export type ImportProviderRead = {
  id: string;
  provider_type: string;
  name: string;
  base_url: string | null;
  api_key_configured: boolean;
  api_key_last4: string | null;
  enabled: boolean;
  created_at: string;
};

export type ImportedProductAdminRead = {
  id: string;
  provider_id: string;
  provider_name: string;
  external_id: string | null;
  external_url: string | null;
  name: string;
  description: string;
  image_url: string | null;
  price_cents: number;
  credit_discount_percentage: number;
  status: "ACTIVE" | "INACTIVE";
  created_at: string;
};

export type ImportedProductRead = {
  id: string;
  name: string;
  description: string;
  image_url: string | null;
  price_cents: number;
  credit_discount_percentage: number;
};

export type ImportedOrderRead = {
  id: string;
  customer_user_id: string;
  customer_display_name: string;
  imported_product_id: string;
  product_name: string;
  product_image_url: string | null;
  created_by_user_id: string;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
};

export type ImportedOrderQuoteRead = {
  imported_product_id: string;
  product_name: string;
  amount_cents: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_available: boolean;
  card_available: boolean;
};

export type FinancialMovementRead = {
  id: string;
  /** CONTRACT_PAYMENT: one paid instalment of a Lial Energy contract (Session 54). */
  kind: "WALLET" | "ORDER_PAYMENT" | "REDEMPTION_PAYMENT" | "CONTRACT_PAYMENT";
  type: string | null;
  source: string | null;
  payment_method: "BANK_TRANSFER" | "CARD" | null;
  amount_cents: number;
  currency: "LIALCASH" | "EUR";
  product_name: string | null;
  order_id: string | null;
  invoice_redemption_id: string | null;
  contract_id?: string | null;
  contract_request_id?: string | null;
  note: string | null;
  customer_user_id: string | null;
  customer_display_name: string | null;
  created_at: string;
};

/** The totals at the top of "Contabilità", computed server-side (Session 54). */
export type AccountingSummaryRead = {
  spent_total_cents: number;
  spent_card_cents: number;
  spent_bank_transfer_cents: number;
  spent_this_month_cents: number;
  spent_orders_cents: number;
  spent_redemptions_cents: number;
  spent_contracts_cents: number;
  payments_count: number;
  lialcash_balance_cents: number;
  lialcash_received_cents: number;
  lialcash_spent_cents: number;
  cashback_received_cents: number;
  contracts_active: number;
  instalments_paid: number;
  next_instalment_due_date: string | null;
  next_instalment_cents: number | null;
  /** Null unless the account is also a promoter. */
  commissions_total_cents: number | null;
  commissions_to_collect_cents: number | null;
  commissions_paid_cents: number | null;
  commissions_count: number | null;
};

/** Everything about one movement, or about the order / cashback redemption /
    contract it refers to -- the "Contabilità" detail popup. */
export type AccountingDetailRead = {
  ref: string;
  kind: "WALLET" | "ORDER" | "REDEMPTION" | "CONTRACT";
  title: string;
  subtitle: string | null;
  status: string | null;
  status_tone: "success" | "warning" | "danger" | "neutral";
  amount_cents: number | null;
  currency: "EUR" | "LIALCASH";
  direction: "in" | "out" | null;
  facts: { label: string; value: string; mono: boolean }[];
  timeline: { label: string; at: string | null; by: string | null; tone: "done" | "pending" | "warning" }[];
  instalments: {
    number: number;
    instalments_total: number;
    due_date: string;
    amount_cents: number;
    status: string;
    paid_at: string | null;
    source: string | null;
    confirmed_by: string | null;
  }[];
  related_refs: string[];
  tab: "orders" | "cashback" | "contracts" | "wallet" | null;
  order_id: string | null;
  invoice_redemption_id: string | null;
  contract_id: string | null;
};

export type InvoiceRedemptionRead = {
  id: string;
  partner_id: string;
  partner_name: string;
  customer_user_id: string;
  customer_display_name: string;
  original_filename: string;
  content_type: string;
  declared_amount_cents: number;
  confirmed_amount_cents: number | null;
  payment_due_cents: number | null;
  payment_reference_code: string | null;
  payment_method: "BANK_TRANSFER" | "CARD" | null;
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  status: "SUBMITTED" | "PAYMENT_PENDING" | "CREDITED" | "REJECTED";
  rejection_reason: string | null;
  created_at: string;
  verified_at: string | null;
  credited_at: string | null;
};


// --- "Invita un amico" (Session 39) ----------------------------------------
// A one-level list every account has, deliberately separate from the
// commercial network: no hierarchy, no commissions. See
// apps/api/app/domains/friend_referrals/models.py.

export type FriendReferralItemRead = {
  id: string;
  display_name: string;
  /** INVITED / IN_PROGRESS / ACTIVE -- only ACTIVE counts towards the gift. */
  state: string;
  /** PROMOTER_LINK / FRIEND_LINK -- which of the two kinds of link was used. */
  source: string;
  invited_at: string;
};

export type FriendReferralClaimRead = {
  id: string;
  milestone: number;
  status: "REQUESTED" | "FULFILLED" | "REJECTED";
  note: string | null;
  requested_at: string;
  handled_at: string | null;
};

export type FriendReferralSummaryRead = {
  code: string;
  invited_total: number;
  active_total: number;
  reward_every: number;
  /** What the gift is, in the customer's words -- server-owned, never
      hardcoded here (see friend_referrals/models.py::REWARD_DESCRIPTION). */
  reward_description: string;
  missing_for_next_reward: number;
  claimable_milestone: number | null;
  referrals: FriendReferralItemRead[];
  claims: FriendReferralClaimRead[];
};

export type FriendReferralAdminClaimRead = {
  id: string;
  referrer_user_id: string;
  referrer_name: string;
  referrer_email: string | null;
  milestone: number;
  status: "REQUESTED" | "FULFILLED" | "REJECTED";
  note: string | null;
  requested_at: string;
  handled_at: string | null;
};


// --- Contratto di collaborazione "Lavora con noi" (Session 40) -------------
// The legal text is served by the backend (structured blocks, never markup)
// so there is exactly one copy of it and changing it needs no frontend
// release. See apps/api/app/domains/network/collaboration_documents.py.

export type CollaborationDocumentBlock =
  | { type: "heading"; text: string }
  | { type: "paragraph"; text: string }
  | { type: "clause"; number: string; text: string }
  | { type: "bullets"; items: string[] }
  | { type: "table"; columns: string[]; rows: string[][]; caption: string | null }
  | { type: "signature"; text: string };

export type CollaborationDocumentRead = {
  key: string;
  /** Echoed back on submit: the record stores WHICH TEXT was agreed to, not
      just that a box was ticked. */
  version: string;
  title: string;
  subtitle: string;
  acceptance_label: string;
  blocks: CollaborationDocumentBlock[];
};


// --- Pagamento del contratto (Session 44) ----------------------------------
// Contracts only; the Shop checkout is separate and unchanged. Every amount
// is computed server-side from the figure frozen on the contract -- the
// browser sends back a plan key and nothing else.

export type ContractPaymentOptionRead = {
  /** FULL / INSTALMENTS_3 / MONTHLY_12 */
  key: string;
  label: string;
  description: string;
  instalments: number;
  instalment_cents: number;
  total_cents: number;
  /** Difference between this plan's total and the contract's own amount,
      caused by rounding an instalment to the cent. Shown, never hidden. */
  rounding_difference_cents: number;
};

export type ContractPaymentOptionsRead = {
  contract_id: string;
  payable: boolean;
  status: string;
  /** At the payment step but with no frozen amount -- a contract created
      before the price snapshot existed. Distinct from "not payable" so the
      message can say whose problem it is. */
  missing_amount: boolean;
  gross_amount_cents: number | null;
  card_available: boolean;
  options: ContractPaymentOptionRead[];
  /** Set once Stripe confirmed the (first) payment -- possibly while the
      documents are still waiting for approval (Session 49). */
  paid_at: string | null;
  payment_plan: string | null;
  /** Automatic LialCash on this contract: the percentage, and what it comes
      to on the whole amount. On instalments it is credited rata per rata. */
  cashback_percentage: number;
  cashback_total_cents: number;
};


// --- Anteprima provvigioni e rate del contratto (Session 50) ---------------
// Computed entirely server-side (commissions/services/preview.py). The
// dashboard only renders it and sends back its checksum on acceptance.

export type CommissionPreviewBeneficiary = {
  agent_id: string;
  name: string;
  rank_code: string;
  depth: number;
  role: string;
  movement_type: string;
  movement_label: string;
  total_cents: number;
  explanation: string;
};

export type CommissionPreviewScheduleRow = {
  number: number;
  due_date: string | null;
  customer_amount_cents: number;
  commission_cents: number;
  per_beneficiary_cents: Record<string, number>;
  release: string;
};

export type CommissionPreviewRead = {
  contract_id: string;
  customer_name: string;
  gross_amount_cents: number;
  beneficiaries: CommissionPreviewBeneficiary[];
  first_referrer_bonus: { agent_id: string; name: string; amount_cents: number; note: string } | null;
  total_commission_cents: number;
  payment: {
    paid: boolean;
    paid_at: string | null;
    plan_key: string | null;
    plan_label: string | null;
    instalments: number | null;
    schedule: CommissionPreviewScheduleRow[];
    last_release_date: string | null;
    scenarios: { plan_key: string; plan_label: string; instalments: number; commission_per_instalment_cents: number }[];
  };
  customer_cashback_cents: number;
  warnings: string[];
  checksum: string;
  /** Only on GET /commission-preview. */
  already_accepted?: boolean;
};

export type ContractInstalmentRead = {
  number: number;
  instalments_total: number;
  due_date: string;
  amount_cents: number;
  /** SCHEDULED / PAID / FAILED */
  status: string;
  paid_at: string | null;
  /** STRIPE_CHECKOUT / STRIPE_INVOICE / ADMIN */
  payment_source: string | null;
  confirmed_by: string | null;
  commission_released_at: string | null;
  commission_pending: boolean;
};

export type ContractCommissionLogRead = {
  contract_id: string;
  status: string;
  payment_plan: string | null;
  accepted_plan: {
    accepted_at: string;
    accepted_by: string | null;
    total_commission_cents: number;
    preview: CommissionPreviewRead;
  } | null;
  instalments: ContractInstalmentRead[];
};

// --- Shop Lial Partner (CJ Dropshipping, Session 60) ---------------------------------

export type CjSettingsRead = {
  api_key_configured: boolean;
  api_key_hint: string | null;
  connected: boolean;
  token_expires_at: string | null;
  enabled: boolean;
  sandbox: boolean;
  usd_eur_rate: number;
  markup_percentage: number;
  markup_fixed_cents: number;
  price_rounding: "90" | "99" | "NONE";
  shipping_mode: "CUSTOMER_PAYS" | "INCLUDED";
  default_credit_percentage: number;
  destination_country: string;
  auto_forward: boolean;
  last_balance_usd: number | null;
  last_balance_at: string | null;
};

export type CjCatalogItem = {
  pid: string;
  name_en: string;
  sku: string;
  image_url: string | null;
  sell_price_usd: string;
  estimated_price_cents: number | null;
  inventory: number | null;
  category_name: string | null;
  free_shipping: boolean;
  already_imported: boolean;
};

export type CjCatalogPage = {
  page: number;
  total_pages: number;
  total_records: number;
  items: CjCatalogItem[];
};

export type CjProductPreview = {
  pid: string;
  sku: string;
  name_en: string;
  description_text: string;
  category_name: string | null;
  images: string[];
  origin_country: string;
  shipping_estimate_usd: number | null;
  shipping_estimate_cents: number | null;
  shipping_days: string | null;
  shipping_carrier: string | null;
  ships_to_destination: boolean;
  variants: {
    vid: string;
    sku: string;
    label: string;
    image_url: string | null;
    cost_usd: number;
    weight_g: number;
    inventory: number;
    price_cents: number;
  }[];
};

export type CjVariantAdminRead = {
  id: string;
  cj_vid: string;
  cj_sku: string | null;
  label: string;
  image_url: string | null;
  cost_usd: number;
  weight_g: number;
  price_cents: number;
  price_override_cents: number | null;
  effective_price_cents: number;
  inventory: number;
  active: boolean;
  available_on_cj: boolean;
};

export type CjProductAdminRead = {
  id: string;
  cj_pid: string;
  cj_sku: string | null;
  name: string;
  name_en: string | null;
  description: string;
  image_url: string | null;
  images: string[];
  category_name: string | null;
  origin_country: string;
  shipping_estimate_usd: number | null;
  shipping_days: string | null;
  status: "ACTIVE" | "INACTIVE";
  credit_discount_percentage: number;
  markup_percentage: number | null;
  last_synced_at: string | null;
  sync_error: string | null;
  paid_orders: number;
  created_at: string;
  variants: CjVariantAdminRead[];
};

export type CjProductRead = {
  id: string;
  name: string;
  description: string;
  image_url: string | null;
  images: string[];
  min_price_cents: number;
  max_price_cents: number;
  credit_discount_percentage: number;
  shipping_days: string | null;
  shipping_included: boolean;
  in_stock: boolean;
  variants: { id: string; label: string; image_url: string | null; price_cents: number; in_stock: boolean }[];
};

export type CjQuoteRead = {
  variant_id: string;
  product_name: string;
  variant_label: string;
  quantity: number;
  unit_price_cents: number;
  items_cents: number;
  shipping_cents: number;
  shipping_included: boolean;
  shipping_days: string | null;
  amount_cents: number;
  credit_discount_percentage: number;
  max_creditable_cents: number;
  customer_wallet_balance_cents: number;
  bank_transfer_available: boolean;
  card_available: boolean;
  default_address: { street: string | null; city: string | null; province: string | null; postal_code: string | null };
};

export type CjFulfillmentStatus =
  | "NOT_SENT" | "SENDING" | "SENT" | "PROCESSING" | "SHIPPED" | "DELIVERED" | "ERROR" | "CJ_CANCELLED";

export type CjDeliveryStatus = "RECEIVED" | "PREPARING" | "SHIPPED" | "DELIVERED" | "PROBLEM";

export type CjPaymentStatus = "NOT_REQUIRED" | "PENDING" | "PAYMENT_REQUIRED" | "PAID" | "FAILED";

export type CjCashSummary = {
  orders_to_pay: number;
  orders_payment_required: number;
  required_usd: number;
  required_cents: number;
  balance_usd: number | null;
  balance_at: string | null;
  shortfall_usd: number;
  shortfall_cents: number;
  sandbox: boolean;
  auto_forward: boolean;
};

export type CjOrderRead = {
  id: string;
  customer_user_id: string;
  customer_display_name: string;
  cj_product_id: string;
  cj_variant_id: string;
  product_name: string;
  product_image_url: string | null;
  variant_label: string | null;
  created_by_user_id: string;
  quantity: number;
  unit_price_cents: number;
  shipping_cents: number;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
  stripe_checkout_session_id: string | null;
  payment_proof_uploaded_at: string | null;
  note: string | null;
  paid_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_at: string;
  recipient_name: string;
  recipient_phone: string | null;
  address_line1: string;
  address_line2: string | null;
  city: string;
  province: string;
  postal_code: string;
  country_code: string;
  shipping_days: string | null;
  /** The only shipping state a customer sees: RECEIVED until the supplier
      is paid (whatever the reason), then PREPARING, SHIPPED, DELIVERED. */
  delivery_status: CjDeliveryStatus | null;
  tracking_number: string | null;
  tracking_url: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
  // Admin only
  fulfillment_status?: CjFulfillmentStatus;
  cj_payment_status?: CjPaymentStatus;
  cj_cost_usd?: number;
  cj_cost_is_actual?: boolean;
  cj_cost_cents?: number;
  cj_order_code?: string | null;
  cj_pay_url?: string | null;
  cj_product_amount_usd?: number | null;
  cj_postage_amount_usd?: number | null;
  cj_ioss_amount_usd?: number | null;
  cj_paid_at?: string | null;
  attempt_count?: number;
  last_attempt_at?: string | null;
  next_retry_at?: string | null;
  last_error_kind?: string | null;
  cj_order_id?: string | null;
  cj_order_status?: string | null;
  cj_amount_usd?: number | null;
  sandbox?: boolean;
  logistic_name?: string;
  origin_country?: string;
  unit_cost_usd?: number;
  shipping_cost_usd?: number;
  usd_eur_rate?: number;
  estimated_margin_cents?: number;
  forwarded_at?: string | null;
  forward_error?: string | null;
  last_cj_sync_at?: string | null;
};
