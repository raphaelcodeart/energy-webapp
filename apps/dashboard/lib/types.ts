// Mirrors the Pydantic response schemas in apps/api/app/domains/*/schemas.py.
// Kept hand-written for this vertical slice; generating from the OpenAPI schema
// (packages/api-client) is tracked as Phase F follow-up work.

export type ContractRead = {
  id: string;
  customer_id: string;
  supply_point_id: string;
  product_version_id: string;
  status: string;
  notes: string | null;
  created_at: string;
  activated_at: string | null;
  expires_at: string | null;
  product_name: string | null;
  supply_point_label: string | null;
  iban: string | null;
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
  created_at: string;
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
  reverses_transaction_id: string | null;
  note: string | null;
  actor_user_id: string | null;
  created_at: string;
};

export type OrganizationSettingsRead = {
  bank_iban: string | null;
  bank_account_holder: string | null;
  bank_transfer_instructions: string | null;
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
  created_by_user_id: string;
  amount_cents: number;
  credit_applied_cents: number;
  residual_amount_cents: number;
  status: "AWAITING_PAYMENT" | "PAID" | "CANCELLED";
  payment_method: "BANK_TRANSFER" | "CARD";
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
  status: "SUBMITTED" | "PAYMENT_PENDING" | "CREDITED" | "REJECTED";
  rejection_reason: string | null;
  created_at: string;
  verified_at: string | null;
  credited_at: string | null;
};

