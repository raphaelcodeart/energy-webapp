--
-- PostgreSQL database dump
--

\restrict ztagYhvccX6Vijx3SgLf843zw1AEUemTUbDxynRT1Z1QWkI2qOCWlsJNefAVrpY

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: addresses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.addresses (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    street character varying(255) NOT NULL,
    city character varying(128) NOT NULL,
    province character varying(8) NOT NULL,
    postal_code character varying(16) NOT NULL,
    country character varying(2) NOT NULL,
    id uuid NOT NULL
);


--
-- Name: agent_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_profiles (
    organization_id uuid NOT NULL,
    user_id uuid,
    display_name character varying(255) NOT NULL,
    promoter_code character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    photo_url character varying(1000),
    joined_at timestamp with time zone NOT NULL,
    current_rank_id uuid,
    approved_by_user_id uuid,
    approved_at timestamp with time zone,
    rejection_reason character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    is_blacklisted boolean DEFAULT false NOT NULL,
    first_name character varying(120),
    last_name character varying(120)
);


--
-- Name: agent_rank_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_rank_history (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    rank_id uuid NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    calculation_source character varying(32) NOT NULL,
    rule_version_id character varying(32) NOT NULL,
    approved_by uuid,
    reason character varying(500),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: attribution_corrections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attribution_corrections (
    organization_id uuid NOT NULL,
    customer_attribution_id uuid NOT NULL,
    previous_promoter_code_id uuid NOT NULL,
    new_promoter_code_id uuid NOT NULL,
    requested_by uuid NOT NULL,
    approved_by uuid,
    reason character varying(500) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    organization_id uuid NOT NULL,
    actor_user_id uuid,
    action character varying(128) NOT NULL,
    entity_type character varying(64) NOT NULL,
    entity_id character varying(64) NOT NULL,
    previous_value jsonb,
    new_value jsonb,
    reason character varying(500),
    ip_address character varying(64),
    user_agent character varying(255),
    correlation_id character varying(64),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_adjustments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_adjustments (
    organization_id uuid NOT NULL,
    original_movement_id uuid NOT NULL,
    new_movement_id uuid NOT NULL,
    reason character varying(500) NOT NULL,
    requested_by uuid NOT NULL,
    approved_by uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_calculation_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_calculation_steps (
    calculation_id uuid NOT NULL,
    step_order integer NOT NULL,
    beneficiary_agent_id uuid NOT NULL,
    rank_at_calculation character varying(16),
    base_amount_cents bigint NOT NULL,
    already_distributed_cents bigint NOT NULL,
    entrepreneurial_difference_cents bigint NOT NULL,
    personal_bonus_cents bigint NOT NULL,
    gross_amount_cents bigint NOT NULL,
    movement_type character varying(32) NOT NULL,
    explanation character varying(1000) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_calculations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_calculations (
    organization_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    network_snapshot_id uuid NOT NULL,
    commission_plan_version_id uuid,
    trigger_event_id uuid NOT NULL,
    input_snapshot jsonb NOT NULL,
    output_snapshot jsonb NOT NULL,
    checksum character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_movements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_movements (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    origin_event_id uuid NOT NULL,
    calculation_id uuid NOT NULL,
    movement_type character varying(32) NOT NULL,
    amount_cents bigint NOT NULL,
    currency character varying(3) NOT NULL,
    status character varying(32) NOT NULL,
    effective_date date NOT NULL,
    scheduled_date date,
    paid_date date,
    rule_version_id character varying(32) NOT NULL,
    network_snapshot_id uuid NOT NULL,
    idempotency_key character varying(128) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_offsets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_offsets (
    organization_id uuid NOT NULL,
    debit_movement_id uuid NOT NULL,
    credit_movement_id uuid NOT NULL,
    reason character varying(500) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_plan_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_plan_versions (
    organization_id uuid NOT NULL,
    version_label character varying(32) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    status character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_reversals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_reversals (
    organization_id uuid NOT NULL,
    original_movement_id uuid NOT NULL,
    new_movement_id uuid NOT NULL,
    reason character varying(500) NOT NULL,
    requested_by uuid NOT NULL,
    approved_by uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: commission_rule_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_rule_versions (
    commission_plan_version_id uuid NOT NULL,
    rule_type character varying(64) NOT NULL,
    parameters jsonb NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.companies (
    customer_id uuid NOT NULL,
    company_name character varying(255) NOT NULL,
    legal_form character varying(64),
    sdi_code character varying(16)
);


--
-- Name: contract_attributions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contract_attributions (
    organization_id uuid NOT NULL,
    producer_agent_id uuid NOT NULL,
    attributed_promoter_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: contract_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contract_events (
    contract_id uuid NOT NULL,
    event_type character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: contract_status_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contract_status_history (
    contract_id uuid NOT NULL,
    from_status character varying(32),
    to_status character varying(32) NOT NULL,
    actor_user_id uuid NOT NULL,
    reason character varying(500),
    notes character varying(2000),
    correlation_id character varying(64) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: contracts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contracts (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    supply_point_id uuid NOT NULL,
    product_version_id uuid NOT NULL,
    contract_attribution_id uuid,
    network_snapshot_id uuid,
    status character varying(32) NOT NULL,
    notes character varying(2000),
    iban character varying(34),
    activated_at timestamp with time zone,
    expires_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: customer_attributions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_attributions (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    promoter_code_id uuid NOT NULL,
    referral_session_id uuid,
    attributed_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: customer_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_profiles (
    customer_id uuid NOT NULL,
    first_name character varying(128) NOT NULL,
    last_name character varying(128) NOT NULL
);


--
-- Name: customers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customers (
    organization_id uuid NOT NULL,
    user_id uuid,
    kind character varying(32) NOT NULL,
    fiscal_code character varying(32),
    vat_number character varying(32),
    email character varying(255) NOT NULL,
    phone character varying(32),
    pec character varying(255),
    photo_url character varying(1000),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: documentation_posts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documentation_posts (
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    organization_id uuid NOT NULL,
    title character varying(200) NOT NULL,
    body text,
    audience character varying(16) DEFAULT 'BOTH'::character varying NOT NULL,
    status character varying(16) DEFAULT 'PUBLISHED'::character varying NOT NULL,
    image_url character varying(500),
    pdf_url character varying(500),
    pdf_filename character varying(255),
    video_url character varying(500),
    created_by_user_id uuid NOT NULL
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    organization_id uuid NOT NULL,
    contract_id uuid NOT NULL,
    document_type character varying(32) NOT NULL,
    original_filename character varying(255) NOT NULL,
    storage_key character varying(500) NOT NULL,
    content_type character varying(100) NOT NULL,
    size_bytes bigint NOT NULL,
    uploaded_by_user_id uuid NOT NULL,
    uploaded_by_role character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    reviewed_by_user_id uuid,
    reviewed_at timestamp with time zone,
    review_note character varying(1000),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: domain_outbox; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_outbox (
    organization_id uuid NOT NULL,
    event_type character varying(64) NOT NULL,
    payload jsonb NOT NULL,
    processed_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: invoice_redemptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.invoice_redemptions (
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    partner_id uuid NOT NULL,
    storage_key character varying(500) NOT NULL,
    original_filename character varying(255) NOT NULL,
    content_type character varying(100) NOT NULL,
    size_bytes bigint NOT NULL,
    declared_amount_cents bigint NOT NULL,
    confirmed_amount_cents bigint,
    payment_reference_code character varying(32),
    status character varying(16) DEFAULT 'SUBMITTED'::character varying NOT NULL,
    rejection_reason character varying(500),
    verified_by_user_id uuid,
    verified_at timestamp with time zone,
    credited_by_user_id uuid,
    credited_at timestamp with time zone,
    CONSTRAINT ck_invoice_redemptions_ck_invoice_redemptions_confirmed_a796 CHECK (((confirmed_amount_cents IS NULL) OR (confirmed_amount_cents > 0)))
);


--
-- Name: network_assignment_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_assignment_history (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    old_parent_agent_id uuid,
    new_parent_agent_id uuid,
    requested_by uuid NOT NULL,
    approved_by uuid,
    reason character varying(500) NOT NULL,
    effective_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: network_closure; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_closure (
    organization_id uuid NOT NULL,
    ancestor_agent_id uuid NOT NULL,
    descendant_agent_id uuid NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    depth integer NOT NULL,
    effective_to timestamp with time zone
);


--
-- Name: network_edges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_edges (
    organization_id uuid NOT NULL,
    parent_agent_id uuid NOT NULL,
    child_agent_id uuid NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: network_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_nodes (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    direct_parent_agent_id uuid,
    status character varying(32) NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    effective_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: network_snapshot_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_snapshot_nodes (
    snapshot_id uuid NOT NULL,
    ancestor_agent_id uuid NOT NULL,
    depth integer NOT NULL,
    rank_id_at_snapshot uuid
);


--
-- Name: network_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.network_snapshots (
    organization_id uuid NOT NULL,
    reason character varying(64) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    organization_id uuid NOT NULL,
    recipient_user_id uuid NOT NULL,
    type character varying(64) NOT NULL,
    entity_type character varying(64) NOT NULL,
    entity_id character varying(64) NOT NULL,
    title character varying(255) NOT NULL,
    body character varying(1000),
    is_read boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    organization_id uuid NOT NULL,
    customer_user_id uuid NOT NULL,
    product_version_id uuid NOT NULL,
    created_by_user_id uuid NOT NULL,
    amount_cents bigint NOT NULL,
    credit_applied_cents bigint DEFAULT '0'::bigint NOT NULL,
    credit_debit_transaction_id uuid,
    status character varying(16) DEFAULT 'AWAITING_PAYMENT'::character varying NOT NULL,
    note character varying(1000),
    paid_by_user_id uuid,
    paid_at timestamp with time zone,
    cancelled_by_user_id uuid,
    cancelled_at timestamp with time zone,
    cancellation_reason character varying(500),
    payment_method character varying(16) DEFAULT 'BANK_TRANSFER'::character varying NOT NULL,
    stripe_checkout_session_id character varying(255),
    CONSTRAINT ck_orders_ck_orders_credit_applied_non_negative CHECK ((credit_applied_cents >= 0)),
    CONSTRAINT ck_orders_ck_orders_credit_applied_not_over_amount CHECK ((credit_applied_cents <= amount_cents))
);


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    name character varying(255) NOT NULL,
    legal_name character varying(255),
    vat_number character varying(32),
    status character varying(32) NOT NULL,
    settings jsonb NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: partners; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.partners (
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    organization_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    logo_url character varying(1000),
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_tokens (
    user_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.permissions (
    code character varying(64) NOT NULL,
    description character varying(255) NOT NULL,
    id uuid NOT NULL
);


--
-- Name: product_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_versions (
    product_id uuid NOT NULL,
    version_label character varying(32) NOT NULL,
    name character varying(255) NOT NULL,
    description character varying(2000) NOT NULL,
    image_url character varying(1000),
    base_price_cents bigint NOT NULL,
    initial_fee_cents bigint NOT NULL,
    recurring_fee_cents bigint NOT NULL,
    billing_period character varying(16) NOT NULL,
    contract_duration_months integer,
    tax_configuration jsonb NOT NULL,
    commission_plan_version_id uuid,
    required_documents jsonb NOT NULL,
    terms_version character varying(32) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    status character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    commission_tokens jsonb DEFAULT '{}'::jsonb NOT NULL,
    credit_discount_percentage integer DEFAULT 0 NOT NULL
);


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    organization_id uuid NOT NULL,
    code character varying(64) NOT NULL,
    product_type character varying(32) NOT NULL,
    energy_type character varying(16),
    customer_type character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    category character varying(16) DEFAULT 'INTERNAL'::character varying NOT NULL
);


--
-- Name: promoter_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.promoter_codes (
    organization_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    code character varying(32) NOT NULL,
    personal_link character varying(500) NOT NULL,
    qr_code_url character varying(500),
    status character varying(32) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: ranks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ranks (
    organization_id uuid NOT NULL,
    code character varying(16) NOT NULL,
    name character varying(128) NOT NULL,
    level integer NOT NULL,
    personal_token_cents bigint NOT NULL,
    energy_share_percentage numeric(5,2) NOT NULL,
    personal_volume_threshold_cents bigint NOT NULL,
    group_volume_threshold_cents bigint NOT NULL,
    evaluation_window_months integer NOT NULL,
    single_branch_cap_percentage numeric(5,2) NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    rule_version character varying(32) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: referral_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_events (
    organization_id uuid NOT NULL,
    promoter_code_id uuid NOT NULL,
    ip_address character varying(64),
    user_agent character varying(255),
    occurred_at timestamp with time zone NOT NULL,
    id uuid NOT NULL
);


--
-- Name: referral_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_sessions (
    organization_id uuid NOT NULL,
    promoter_code_id uuid NOT NULL,
    cookie_token_hash character varying(64) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: role_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_permissions (
    role_id uuid NOT NULL,
    permission_id uuid NOT NULL
);


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    organization_id uuid,
    code character varying(64) NOT NULL,
    name character varying(128) NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sessions (
    user_id uuid NOT NULL,
    refresh_token_hash character varying(64) NOT NULL,
    user_agent character varying(255),
    ip_address character varying(64),
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: supply_points; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.supply_points (
    organization_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    label character varying(255),
    energy_type character varying(16) NOT NULL,
    pod_code character varying(32),
    pdr_code character varying(32),
    meter_number character varying(64),
    supply_address_id uuid NOT NULL,
    estimated_consumption bigint,
    actual_consumption bigint,
    provider_reference character varying(128),
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: ticket_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ticket_messages (
    ticket_id uuid NOT NULL,
    author_user_id uuid NOT NULL,
    author_role character varying(32) NOT NULL,
    body text NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tickets (
    organization_id uuid NOT NULL,
    opened_by_user_id uuid NOT NULL,
    opened_by_role character varying(32) NOT NULL,
    subject character varying(255) NOT NULL,
    category character varying(32) NOT NULL,
    status character varying(16) NOT NULL,
    contract_id uuid,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: user_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_roles (
    user_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    role_id uuid NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    organization_id uuid NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    status character varying(32) NOT NULL,
    email_verified_at timestamp with time zone,
    failed_login_attempts integer NOT NULL,
    locked_until timestamp with time zone,
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: wallet_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wallet_transactions (
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    organization_id uuid NOT NULL,
    from_wallet_id uuid,
    to_wallet_id uuid,
    amount_cents bigint NOT NULL,
    currency character varying(3) DEFAULT 'EUR'::character varying NOT NULL,
    type character varying(16) NOT NULL,
    reference_contract_id uuid,
    reverses_transaction_id uuid,
    note character varying(500),
    actor_user_id uuid,
    idempotency_key character varying(128) NOT NULL,
    source character varying(32),
    reference_invoice_redemption_id uuid,
    reference_order_id uuid,
    CONSTRAINT ck_wallet_transactions_ck_wallet_transactions_has_a_side CHECK (((from_wallet_id IS NOT NULL) OR (to_wallet_id IS NOT NULL)))
);


--
-- Name: wallets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wallets (
    id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL,
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    address character varying(42) NOT NULL,
    balance_cents bigint DEFAULT '0'::bigint NOT NULL,
    currency character varying(3) DEFAULT 'EUR'::character varying NOT NULL,
    can_transfer boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_wallets_ck_wallets_balance_non_negative CHECK ((balance_cents >= 0))
);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: addresses pk_addresses; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.addresses
    ADD CONSTRAINT pk_addresses PRIMARY KEY (id);


--
-- Name: agent_profiles pk_agent_profiles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT pk_agent_profiles PRIMARY KEY (id);


--
-- Name: agent_rank_history pk_agent_rank_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_rank_history
    ADD CONSTRAINT pk_agent_rank_history PRIMARY KEY (id);


--
-- Name: attribution_corrections pk_attribution_corrections; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT pk_attribution_corrections PRIMARY KEY (id);


--
-- Name: audit_log pk_audit_log; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT pk_audit_log PRIMARY KEY (id);


--
-- Name: commission_adjustments pk_commission_adjustments; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT pk_commission_adjustments PRIMARY KEY (id);


--
-- Name: commission_calculation_steps pk_commission_calculation_steps; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculation_steps
    ADD CONSTRAINT pk_commission_calculation_steps PRIMARY KEY (id);


--
-- Name: commission_calculations pk_commission_calculations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT pk_commission_calculations PRIMARY KEY (id);


--
-- Name: commission_movements pk_commission_movements; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT pk_commission_movements PRIMARY KEY (id);


--
-- Name: commission_offsets pk_commission_offsets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_offsets
    ADD CONSTRAINT pk_commission_offsets PRIMARY KEY (id);


--
-- Name: commission_plan_versions pk_commission_plan_versions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_plan_versions
    ADD CONSTRAINT pk_commission_plan_versions PRIMARY KEY (id);


--
-- Name: commission_reversals pk_commission_reversals; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT pk_commission_reversals PRIMARY KEY (id);


--
-- Name: commission_rule_versions pk_commission_rule_versions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_rule_versions
    ADD CONSTRAINT pk_commission_rule_versions PRIMARY KEY (id);


--
-- Name: companies pk_companies; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT pk_companies PRIMARY KEY (customer_id);


--
-- Name: contract_attributions pk_contract_attributions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_attributions
    ADD CONSTRAINT pk_contract_attributions PRIMARY KEY (id);


--
-- Name: contract_events pk_contract_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_events
    ADD CONSTRAINT pk_contract_events PRIMARY KEY (id);


--
-- Name: contract_status_history pk_contract_status_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_status_history
    ADD CONSTRAINT pk_contract_status_history PRIMARY KEY (id);


--
-- Name: contracts pk_contracts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT pk_contracts PRIMARY KEY (id);


--
-- Name: customer_attributions pk_customer_attributions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_attributions
    ADD CONSTRAINT pk_customer_attributions PRIMARY KEY (id);


--
-- Name: customer_profiles pk_customer_profiles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles
    ADD CONSTRAINT pk_customer_profiles PRIMARY KEY (customer_id);


--
-- Name: customers pk_customers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT pk_customers PRIMARY KEY (id);


--
-- Name: documentation_posts pk_documentation_posts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documentation_posts
    ADD CONSTRAINT pk_documentation_posts PRIMARY KEY (id);


--
-- Name: documents pk_documents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT pk_documents PRIMARY KEY (id);


--
-- Name: domain_outbox pk_domain_outbox; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_outbox
    ADD CONSTRAINT pk_domain_outbox PRIMARY KEY (id);


--
-- Name: invoice_redemptions pk_invoice_redemptions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_redemptions
    ADD CONSTRAINT pk_invoice_redemptions PRIMARY KEY (id);


--
-- Name: network_assignment_history pk_network_assignment_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT pk_network_assignment_history PRIMARY KEY (id);


--
-- Name: network_closure pk_network_closure; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_closure
    ADD CONSTRAINT pk_network_closure PRIMARY KEY (organization_id, ancestor_agent_id, descendant_agent_id, effective_from);


--
-- Name: network_edges pk_network_edges; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_edges
    ADD CONSTRAINT pk_network_edges PRIMARY KEY (id);


--
-- Name: network_nodes pk_network_nodes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_nodes
    ADD CONSTRAINT pk_network_nodes PRIMARY KEY (id);


--
-- Name: network_snapshot_nodes pk_network_snapshot_nodes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshot_nodes
    ADD CONSTRAINT pk_network_snapshot_nodes PRIMARY KEY (snapshot_id, ancestor_agent_id);


--
-- Name: network_snapshots pk_network_snapshots; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshots
    ADD CONSTRAINT pk_network_snapshots PRIMARY KEY (id);


--
-- Name: notifications pk_notifications; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT pk_notifications PRIMARY KEY (id);


--
-- Name: orders pk_orders; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT pk_orders PRIMARY KEY (id);


--
-- Name: organizations pk_organizations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT pk_organizations PRIMARY KEY (id);


--
-- Name: partners pk_partners; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.partners
    ADD CONSTRAINT pk_partners PRIMARY KEY (id);


--
-- Name: password_reset_tokens pk_password_reset_tokens; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT pk_password_reset_tokens PRIMARY KEY (id);


--
-- Name: permissions pk_permissions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT pk_permissions PRIMARY KEY (id);


--
-- Name: product_versions pk_product_versions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_versions
    ADD CONSTRAINT pk_product_versions PRIMARY KEY (id);


--
-- Name: products pk_products; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT pk_products PRIMARY KEY (id);


--
-- Name: promoter_codes pk_promoter_codes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promoter_codes
    ADD CONSTRAINT pk_promoter_codes PRIMARY KEY (id);


--
-- Name: ranks pk_ranks; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranks
    ADD CONSTRAINT pk_ranks PRIMARY KEY (id);


--
-- Name: referral_events pk_referral_events; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_events
    ADD CONSTRAINT pk_referral_events PRIMARY KEY (id);


--
-- Name: referral_sessions pk_referral_sessions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_sessions
    ADD CONSTRAINT pk_referral_sessions PRIMARY KEY (id);


--
-- Name: role_permissions pk_role_permissions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT pk_role_permissions PRIMARY KEY (role_id, permission_id);


--
-- Name: roles pk_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT pk_roles PRIMARY KEY (id);


--
-- Name: sessions pk_sessions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT pk_sessions PRIMARY KEY (id);


--
-- Name: supply_points pk_supply_points; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supply_points
    ADD CONSTRAINT pk_supply_points PRIMARY KEY (id);


--
-- Name: ticket_messages pk_ticket_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_messages
    ADD CONSTRAINT pk_ticket_messages PRIMARY KEY (id);


--
-- Name: tickets pk_tickets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT pk_tickets PRIMARY KEY (id);


--
-- Name: user_roles pk_user_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT pk_user_roles PRIMARY KEY (id);


--
-- Name: users pk_users; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT pk_users PRIMARY KEY (id);


--
-- Name: wallet_transactions pk_wallet_transactions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT pk_wallet_transactions PRIMARY KEY (id);


--
-- Name: wallets pk_wallets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT pk_wallets PRIMARY KEY (id);


--
-- Name: agent_profiles uq_agent_promoter_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT uq_agent_promoter_code UNIQUE (organization_id, promoter_code);


--
-- Name: commission_calculations uq_commission_calculations_contract_trigger; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT uq_commission_calculations_contract_trigger UNIQUE (contract_id, trigger_event_id);


--
-- Name: commission_movements uq_commission_movements_idempotency_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT uq_commission_movements_idempotency_key UNIQUE (idempotency_key);


--
-- Name: customers uq_customers_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT uq_customers_user_id UNIQUE (user_id);


--
-- Name: documents uq_documents_storage_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT uq_documents_storage_key UNIQUE (storage_key);


--
-- Name: invoice_redemptions uq_invoice_redemptions_payment_reference_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_redemptions
    ADD CONSTRAINT uq_invoice_redemptions_payment_reference_code UNIQUE (payment_reference_code);


--
-- Name: invoice_redemptions uq_invoice_redemptions_storage_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_redemptions
    ADD CONSTRAINT uq_invoice_redemptions_storage_key UNIQUE (storage_key);


--
-- Name: orders uq_orders_stripe_checkout_session_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT uq_orders_stripe_checkout_session_id UNIQUE (stripe_checkout_session_id);


--
-- Name: partners uq_partners_organization_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.partners
    ADD CONSTRAINT uq_partners_organization_name UNIQUE (organization_id, name);


--
-- Name: permissions uq_permissions_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT uq_permissions_code UNIQUE (code);


--
-- Name: ranks uq_ranks_org_code_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranks
    ADD CONSTRAINT uq_ranks_org_code_version UNIQUE (organization_id, code, rule_version);


--
-- Name: roles uq_roles_org_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT uq_roles_org_code UNIQUE (organization_id, code);


--
-- Name: user_roles uq_user_roles; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT uq_user_roles UNIQUE (user_id, organization_id, role_id);


--
-- Name: users uq_users_org_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_org_email UNIQUE (organization_id, email);


--
-- Name: wallet_transactions uq_wallet_transactions_idempotency_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT uq_wallet_transactions_idempotency_key UNIQUE (idempotency_key);


--
-- Name: wallets uq_wallets_address; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT uq_wallets_address UNIQUE (address);


--
-- Name: wallets uq_wallets_user_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT uq_wallets_user_id UNIQUE (user_id);


--
-- Name: ix_addresses_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_addresses_customer_id ON public.addresses USING btree (customer_id);


--
-- Name: ix_addresses_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_addresses_organization_id ON public.addresses USING btree (organization_id);


--
-- Name: ix_agent_profiles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_profiles_organization_id ON public.agent_profiles USING btree (organization_id);


--
-- Name: ix_agent_rank_history_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_rank_history_agent_id ON public.agent_rank_history USING btree (agent_id);


--
-- Name: ix_agent_rank_history_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_rank_history_organization_id ON public.agent_rank_history USING btree (organization_id);


--
-- Name: ix_attribution_corrections_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attribution_corrections_organization_id ON public.attribution_corrections USING btree (organization_id);


--
-- Name: ix_audit_log_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_log_action ON public.audit_log USING btree (action);


--
-- Name: ix_audit_log_correlation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_log_correlation_id ON public.audit_log USING btree (correlation_id);


--
-- Name: ix_audit_log_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_log_organization_id ON public.audit_log USING btree (organization_id);


--
-- Name: ix_commission_adjustments_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_adjustments_organization_id ON public.commission_adjustments USING btree (organization_id);


--
-- Name: ix_commission_calculation_steps_calculation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_calculation_steps_calculation_id ON public.commission_calculation_steps USING btree (calculation_id);


--
-- Name: ix_commission_calculations_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_calculations_contract_id ON public.commission_calculations USING btree (contract_id);


--
-- Name: ix_commission_calculations_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_calculations_organization_id ON public.commission_calculations USING btree (organization_id);


--
-- Name: ix_commission_movements_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_movements_agent_id ON public.commission_movements USING btree (agent_id);


--
-- Name: ix_commission_movements_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_movements_contract_id ON public.commission_movements USING btree (contract_id);


--
-- Name: ix_commission_movements_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_movements_organization_id ON public.commission_movements USING btree (organization_id);


--
-- Name: ix_commission_offsets_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_offsets_organization_id ON public.commission_offsets USING btree (organization_id);


--
-- Name: ix_commission_plan_versions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_plan_versions_organization_id ON public.commission_plan_versions USING btree (organization_id);


--
-- Name: ix_commission_reversals_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_reversals_organization_id ON public.commission_reversals USING btree (organization_id);


--
-- Name: ix_commission_rule_versions_commission_plan_version_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commission_rule_versions_commission_plan_version_id ON public.commission_rule_versions USING btree (commission_plan_version_id);


--
-- Name: ix_contract_attributions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_attributions_organization_id ON public.contract_attributions USING btree (organization_id);


--
-- Name: ix_contract_events_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_events_contract_id ON public.contract_events USING btree (contract_id);


--
-- Name: ix_contract_status_history_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contract_status_history_contract_id ON public.contract_status_history USING btree (contract_id);


--
-- Name: ix_contracts_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contracts_customer_id ON public.contracts USING btree (customer_id);


--
-- Name: ix_contracts_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contracts_expires_at ON public.contracts USING btree (expires_at);


--
-- Name: ix_contracts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contracts_organization_id ON public.contracts USING btree (organization_id);


--
-- Name: ix_contracts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contracts_status ON public.contracts USING btree (status);


--
-- Name: ix_customer_attributions_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_attributions_customer_id ON public.customer_attributions USING btree (customer_id);


--
-- Name: ix_customer_attributions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customer_attributions_organization_id ON public.customer_attributions USING btree (organization_id);


--
-- Name: ix_customers_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_customers_organization_id ON public.customers USING btree (organization_id);


--
-- Name: ix_documentation_posts_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documentation_posts_organization_id ON public.documentation_posts USING btree (organization_id);


--
-- Name: ix_documentation_posts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documentation_posts_status ON public.documentation_posts USING btree (status);


--
-- Name: ix_documents_contract_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_contract_id ON public.documents USING btree (contract_id);


--
-- Name: ix_documents_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_organization_id ON public.documents USING btree (organization_id);


--
-- Name: ix_documents_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_status ON public.documents USING btree (status);


--
-- Name: ix_domain_outbox_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_domain_outbox_event_type ON public.domain_outbox USING btree (event_type);


--
-- Name: ix_domain_outbox_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_domain_outbox_organization_id ON public.domain_outbox USING btree (organization_id);


--
-- Name: ix_domain_outbox_processed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_domain_outbox_processed_at ON public.domain_outbox USING btree (processed_at);


--
-- Name: ix_invoice_redemptions_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invoice_redemptions_customer_user_id ON public.invoice_redemptions USING btree (customer_user_id);


--
-- Name: ix_invoice_redemptions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invoice_redemptions_organization_id ON public.invoice_redemptions USING btree (organization_id);


--
-- Name: ix_invoice_redemptions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invoice_redemptions_status ON public.invoice_redemptions USING btree (status);


--
-- Name: ix_network_assignment_history_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_assignment_history_organization_id ON public.network_assignment_history USING btree (organization_id);


--
-- Name: ix_network_closure_org_ancestor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_closure_org_ancestor ON public.network_closure USING btree (organization_id, ancestor_agent_id);


--
-- Name: ix_network_closure_org_ancestor_depth; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_closure_org_ancestor_depth ON public.network_closure USING btree (organization_id, ancestor_agent_id, depth);


--
-- Name: ix_network_closure_org_descendant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_closure_org_descendant ON public.network_closure USING btree (organization_id, descendant_agent_id);


--
-- Name: ix_network_closure_org_descendant_depth; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_closure_org_descendant_depth ON public.network_closure USING btree (organization_id, descendant_agent_id, depth);


--
-- Name: ix_network_edges_child_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_edges_child_agent_id ON public.network_edges USING btree (child_agent_id);


--
-- Name: ix_network_edges_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_edges_organization_id ON public.network_edges USING btree (organization_id);


--
-- Name: ix_network_edges_parent_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_edges_parent_agent_id ON public.network_edges USING btree (parent_agent_id);


--
-- Name: ix_network_nodes_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_nodes_agent_id ON public.network_nodes USING btree (agent_id);


--
-- Name: ix_network_nodes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_nodes_organization_id ON public.network_nodes USING btree (organization_id);


--
-- Name: ix_network_snapshots_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_network_snapshots_organization_id ON public.network_snapshots USING btree (organization_id);


--
-- Name: ix_notifications_is_read; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_is_read ON public.notifications USING btree (is_read);


--
-- Name: ix_notifications_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_organization_id ON public.notifications USING btree (organization_id);


--
-- Name: ix_notifications_recipient_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_recipient_user_id ON public.notifications USING btree (recipient_user_id);


--
-- Name: ix_notifications_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_type ON public.notifications USING btree (type);


--
-- Name: ix_orders_customer_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_customer_user_id ON public.orders USING btree (customer_user_id);


--
-- Name: ix_orders_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_organization_id ON public.orders USING btree (organization_id);


--
-- Name: ix_orders_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_orders_status ON public.orders USING btree (status);


--
-- Name: ix_partners_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_partners_organization_id ON public.partners USING btree (organization_id);


--
-- Name: ix_password_reset_tokens_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_password_reset_tokens_token_hash ON public.password_reset_tokens USING btree (token_hash);


--
-- Name: ix_password_reset_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_password_reset_tokens_user_id ON public.password_reset_tokens USING btree (user_id);


--
-- Name: ix_product_versions_product_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_product_versions_product_id ON public.product_versions USING btree (product_id);


--
-- Name: ix_products_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_products_organization_id ON public.products USING btree (organization_id);


--
-- Name: ix_promoter_codes_agent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_promoter_codes_agent_id ON public.promoter_codes USING btree (agent_id);


--
-- Name: ix_promoter_codes_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_promoter_codes_code ON public.promoter_codes USING btree (code);


--
-- Name: ix_promoter_codes_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_promoter_codes_organization_id ON public.promoter_codes USING btree (organization_id);


--
-- Name: ix_ranks_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ranks_organization_id ON public.ranks USING btree (organization_id);


--
-- Name: ix_referral_events_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_referral_events_organization_id ON public.referral_events USING btree (organization_id);


--
-- Name: ix_referral_events_promoter_code_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_referral_events_promoter_code_id ON public.referral_events USING btree (promoter_code_id);


--
-- Name: ix_referral_sessions_cookie_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_referral_sessions_cookie_token_hash ON public.referral_sessions USING btree (cookie_token_hash);


--
-- Name: ix_referral_sessions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_referral_sessions_organization_id ON public.referral_sessions USING btree (organization_id);


--
-- Name: ix_referral_sessions_promoter_code_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_referral_sessions_promoter_code_id ON public.referral_sessions USING btree (promoter_code_id);


--
-- Name: ix_roles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_roles_organization_id ON public.roles USING btree (organization_id);


--
-- Name: ix_sessions_refresh_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_sessions_refresh_token_hash ON public.sessions USING btree (refresh_token_hash);


--
-- Name: ix_sessions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sessions_user_id ON public.sessions USING btree (user_id);


--
-- Name: ix_supply_points_customer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_supply_points_customer_id ON public.supply_points USING btree (customer_id);


--
-- Name: ix_supply_points_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_supply_points_organization_id ON public.supply_points USING btree (organization_id);


--
-- Name: ix_ticket_messages_ticket_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ticket_messages_ticket_id ON public.ticket_messages USING btree (ticket_id);


--
-- Name: ix_tickets_opened_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_opened_by_user_id ON public.tickets USING btree (opened_by_user_id);


--
-- Name: ix_tickets_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_organization_id ON public.tickets USING btree (organization_id);


--
-- Name: ix_tickets_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_tickets_status ON public.tickets USING btree (status);


--
-- Name: ix_user_roles_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_roles_organization_id ON public.user_roles USING btree (organization_id);


--
-- Name: ix_user_roles_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_roles_user_id ON public.user_roles USING btree (user_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_organization_id ON public.users USING btree (organization_id);


--
-- Name: ix_wallet_transactions_from_wallet_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_from_wallet_id ON public.wallet_transactions USING btree (from_wallet_id);


--
-- Name: ix_wallet_transactions_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_organization_id ON public.wallet_transactions USING btree (organization_id);


--
-- Name: ix_wallet_transactions_to_wallet_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_to_wallet_id ON public.wallet_transactions USING btree (to_wallet_id);


--
-- Name: ix_wallet_transactions_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallet_transactions_type ON public.wallet_transactions USING btree (type);


--
-- Name: ix_wallets_address; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallets_address ON public.wallets USING btree (address);


--
-- Name: ix_wallets_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallets_organization_id ON public.wallets USING btree (organization_id);


--
-- Name: ix_wallets_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_wallets_user_id ON public.wallets USING btree (user_id);


--
-- Name: uq_network_nodes_active_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_network_nodes_active_agent ON public.network_nodes USING btree (organization_id, agent_id) WHERE (effective_to IS NULL);


--
-- Name: addresses fk_addresses_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.addresses
    ADD CONSTRAINT fk_addresses_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: addresses fk_addresses_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.addresses
    ADD CONSTRAINT fk_addresses_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: agent_profiles fk_agent_profiles_approved_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT fk_agent_profiles_approved_by_user_id_users FOREIGN KEY (approved_by_user_id) REFERENCES public.users(id);


--
-- Name: agent_profiles fk_agent_profiles_current_rank_id_ranks; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT fk_agent_profiles_current_rank_id_ranks FOREIGN KEY (current_rank_id) REFERENCES public.ranks(id);


--
-- Name: agent_profiles fk_agent_profiles_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT fk_agent_profiles_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: agent_profiles fk_agent_profiles_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_profiles
    ADD CONSTRAINT fk_agent_profiles_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: agent_rank_history fk_agent_rank_history_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_rank_history
    ADD CONSTRAINT fk_agent_rank_history_agent_id_agent_profiles FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: agent_rank_history fk_agent_rank_history_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_rank_history
    ADD CONSTRAINT fk_agent_rank_history_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: agent_rank_history fk_agent_rank_history_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_rank_history
    ADD CONSTRAINT fk_agent_rank_history_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: agent_rank_history fk_agent_rank_history_rank_id_ranks; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_rank_history
    ADD CONSTRAINT fk_agent_rank_history_rank_id_ranks FOREIGN KEY (rank_id) REFERENCES public.ranks(id);


--
-- Name: attribution_corrections fk_attribution_corrections_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: attribution_corrections fk_attribution_corrections_customer_attribution_id_cust_9fdb; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_customer_attribution_id_cust_9fdb FOREIGN KEY (customer_attribution_id) REFERENCES public.customer_attributions(id);


--
-- Name: attribution_corrections fk_attribution_corrections_new_promoter_code_id_promoter_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_new_promoter_code_id_promoter_codes FOREIGN KEY (new_promoter_code_id) REFERENCES public.promoter_codes(id);


--
-- Name: attribution_corrections fk_attribution_corrections_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: attribution_corrections fk_attribution_corrections_previous_promoter_code_id_pr_9ca1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_previous_promoter_code_id_pr_9ca1 FOREIGN KEY (previous_promoter_code_id) REFERENCES public.promoter_codes(id);


--
-- Name: attribution_corrections fk_attribution_corrections_requested_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attribution_corrections
    ADD CONSTRAINT fk_attribution_corrections_requested_by_users FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: audit_log fk_audit_log_actor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT fk_audit_log_actor_user_id_users FOREIGN KEY (actor_user_id) REFERENCES public.users(id);


--
-- Name: audit_log fk_audit_log_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT fk_audit_log_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_adjustments fk_commission_adjustments_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT fk_commission_adjustments_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: commission_adjustments fk_commission_adjustments_new_movement_id_commission_movements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT fk_commission_adjustments_new_movement_id_commission_movements FOREIGN KEY (new_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_adjustments fk_commission_adjustments_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT fk_commission_adjustments_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_adjustments fk_commission_adjustments_original_movement_id_commissi_4113; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT fk_commission_adjustments_original_movement_id_commissi_4113 FOREIGN KEY (original_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_adjustments fk_commission_adjustments_requested_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_adjustments
    ADD CONSTRAINT fk_commission_adjustments_requested_by_users FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: commission_calculation_steps fk_commission_calculation_steps_beneficiary_agent_id_ag_5fea; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculation_steps
    ADD CONSTRAINT fk_commission_calculation_steps_beneficiary_agent_id_ag_5fea FOREIGN KEY (beneficiary_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: commission_calculation_steps fk_commission_calculation_steps_calculation_id_commissi_4b0f; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculation_steps
    ADD CONSTRAINT fk_commission_calculation_steps_calculation_id_commissi_4b0f FOREIGN KEY (calculation_id) REFERENCES public.commission_calculations(id);


--
-- Name: commission_calculations fk_commission_calculations_commission_plan_version_id_c_62c3; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT fk_commission_calculations_commission_plan_version_id_c_62c3 FOREIGN KEY (commission_plan_version_id) REFERENCES public.commission_plan_versions(id);


--
-- Name: commission_calculations fk_commission_calculations_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT fk_commission_calculations_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: commission_calculations fk_commission_calculations_network_snapshot_id_network__9654; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT fk_commission_calculations_network_snapshot_id_network__9654 FOREIGN KEY (network_snapshot_id) REFERENCES public.network_snapshots(id);


--
-- Name: commission_calculations fk_commission_calculations_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_calculations
    ADD CONSTRAINT fk_commission_calculations_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_movements fk_commission_movements_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT fk_commission_movements_agent_id_agent_profiles FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: commission_movements fk_commission_movements_calculation_id_commission_calculations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT fk_commission_movements_calculation_id_commission_calculations FOREIGN KEY (calculation_id) REFERENCES public.commission_calculations(id);


--
-- Name: commission_movements fk_commission_movements_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT fk_commission_movements_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: commission_movements fk_commission_movements_network_snapshot_id_network_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT fk_commission_movements_network_snapshot_id_network_snapshots FOREIGN KEY (network_snapshot_id) REFERENCES public.network_snapshots(id);


--
-- Name: commission_movements fk_commission_movements_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_movements
    ADD CONSTRAINT fk_commission_movements_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_offsets fk_commission_offsets_credit_movement_id_commission_movements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_offsets
    ADD CONSTRAINT fk_commission_offsets_credit_movement_id_commission_movements FOREIGN KEY (credit_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_offsets fk_commission_offsets_debit_movement_id_commission_movements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_offsets
    ADD CONSTRAINT fk_commission_offsets_debit_movement_id_commission_movements FOREIGN KEY (debit_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_offsets fk_commission_offsets_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_offsets
    ADD CONSTRAINT fk_commission_offsets_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_plan_versions fk_commission_plan_versions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_plan_versions
    ADD CONSTRAINT fk_commission_plan_versions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_reversals fk_commission_reversals_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT fk_commission_reversals_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: commission_reversals fk_commission_reversals_new_movement_id_commission_movements; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT fk_commission_reversals_new_movement_id_commission_movements FOREIGN KEY (new_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_reversals fk_commission_reversals_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT fk_commission_reversals_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: commission_reversals fk_commission_reversals_original_movement_id_commission_9fb0; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT fk_commission_reversals_original_movement_id_commission_9fb0 FOREIGN KEY (original_movement_id) REFERENCES public.commission_movements(id);


--
-- Name: commission_reversals fk_commission_reversals_requested_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_reversals
    ADD CONSTRAINT fk_commission_reversals_requested_by_users FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: commission_rule_versions fk_commission_rule_versions_commission_plan_version_id__cf5f; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_rule_versions
    ADD CONSTRAINT fk_commission_rule_versions_commission_plan_version_id__cf5f FOREIGN KEY (commission_plan_version_id) REFERENCES public.commission_plan_versions(id);


--
-- Name: companies fk_companies_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT fk_companies_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: contract_attributions fk_contract_attributions_attributed_promoter_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_attributions
    ADD CONSTRAINT fk_contract_attributions_attributed_promoter_id_agent_profiles FOREIGN KEY (attributed_promoter_id) REFERENCES public.agent_profiles(id);


--
-- Name: contract_attributions fk_contract_attributions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_attributions
    ADD CONSTRAINT fk_contract_attributions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: contract_attributions fk_contract_attributions_producer_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_attributions
    ADD CONSTRAINT fk_contract_attributions_producer_agent_id_agent_profiles FOREIGN KEY (producer_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: contract_events fk_contract_events_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_events
    ADD CONSTRAINT fk_contract_events_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: contract_status_history fk_contract_status_history_actor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_status_history
    ADD CONSTRAINT fk_contract_status_history_actor_user_id_users FOREIGN KEY (actor_user_id) REFERENCES public.users(id);


--
-- Name: contract_status_history fk_contract_status_history_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contract_status_history
    ADD CONSTRAINT fk_contract_status_history_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: contracts fk_contracts_contract_attribution_id_contract_attributions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_contract_attribution_id_contract_attributions FOREIGN KEY (contract_attribution_id) REFERENCES public.contract_attributions(id);


--
-- Name: contracts fk_contracts_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: contracts fk_contracts_network_snapshot_id_network_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_network_snapshot_id_network_snapshots FOREIGN KEY (network_snapshot_id) REFERENCES public.network_snapshots(id);


--
-- Name: contracts fk_contracts_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: contracts fk_contracts_product_version_id_product_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_product_version_id_product_versions FOREIGN KEY (product_version_id) REFERENCES public.product_versions(id);


--
-- Name: contracts fk_contracts_supply_point_id_supply_points; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contracts
    ADD CONSTRAINT fk_contracts_supply_point_id_supply_points FOREIGN KEY (supply_point_id) REFERENCES public.supply_points(id);


--
-- Name: customer_attributions fk_customer_attributions_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_attributions
    ADD CONSTRAINT fk_customer_attributions_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: customer_attributions fk_customer_attributions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_attributions
    ADD CONSTRAINT fk_customer_attributions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: customer_attributions fk_customer_attributions_promoter_code_id_promoter_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_attributions
    ADD CONSTRAINT fk_customer_attributions_promoter_code_id_promoter_codes FOREIGN KEY (promoter_code_id) REFERENCES public.promoter_codes(id);


--
-- Name: customer_attributions fk_customer_attributions_referral_session_id_referral_sessions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_attributions
    ADD CONSTRAINT fk_customer_attributions_referral_session_id_referral_sessions FOREIGN KEY (referral_session_id) REFERENCES public.referral_sessions(id);


--
-- Name: customer_profiles fk_customer_profiles_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_profiles
    ADD CONSTRAINT fk_customer_profiles_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: customers fk_customers_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT fk_customers_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: customers fk_customers_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT fk_customers_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: documentation_posts fk_documentation_posts_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documentation_posts
    ADD CONSTRAINT fk_documentation_posts_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: documentation_posts fk_documentation_posts_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documentation_posts
    ADD CONSTRAINT fk_documentation_posts_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: documents fk_documents_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: documents fk_documents_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: documents fk_documents_reviewed_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_reviewed_by_user_id_users FOREIGN KEY (reviewed_by_user_id) REFERENCES public.users(id);


--
-- Name: documents fk_documents_uploaded_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT fk_documents_uploaded_by_user_id_users FOREIGN KEY (uploaded_by_user_id) REFERENCES public.users(id);


--
-- Name: domain_outbox fk_domain_outbox_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_outbox
    ADD CONSTRAINT fk_domain_outbox_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: invoice_redemptions fk_invoice_redemptions_credited_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_redemptions
    ADD CONSTRAINT fk_invoice_redemptions_credited_by_user_id_users FOREIGN KEY (credited_by_user_id) REFERENCES public.users(id);


--
-- Name: invoice_redemptions fk_invoice_redemptions_customer_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_redemptions
    ADD CONSTRAINT fk_invoice_redemptions_customer_user_id_users FOREIGN KEY (customer_user_id) REFERENCES public.users(id);


--
-- Name: invoice_redemptions fk_invoice_redemptions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_redemptions
    ADD CONSTRAINT fk_invoice_redemptions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: invoice_redemptions fk_invoice_redemptions_partner_id_partners; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_redemptions
    ADD CONSTRAINT fk_invoice_redemptions_partner_id_partners FOREIGN KEY (partner_id) REFERENCES public.partners(id);


--
-- Name: invoice_redemptions fk_invoice_redemptions_verified_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoice_redemptions
    ADD CONSTRAINT fk_invoice_redemptions_verified_by_user_id_users FOREIGN KEY (verified_by_user_id) REFERENCES public.users(id);


--
-- Name: network_assignment_history fk_network_assignment_history_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_agent_id_agent_profiles FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_assignment_history fk_network_assignment_history_approved_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_approved_by_users FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: network_assignment_history fk_network_assignment_history_new_parent_agent_id_agent_149a; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_new_parent_agent_id_agent_149a FOREIGN KEY (new_parent_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_assignment_history fk_network_assignment_history_old_parent_agent_id_agent_6886; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_old_parent_agent_id_agent_6886 FOREIGN KEY (old_parent_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_assignment_history fk_network_assignment_history_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: network_assignment_history fk_network_assignment_history_requested_by_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_assignment_history
    ADD CONSTRAINT fk_network_assignment_history_requested_by_users FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: network_closure fk_network_closure_ancestor_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_closure
    ADD CONSTRAINT fk_network_closure_ancestor_agent_id_agent_profiles FOREIGN KEY (ancestor_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_closure fk_network_closure_descendant_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_closure
    ADD CONSTRAINT fk_network_closure_descendant_agent_id_agent_profiles FOREIGN KEY (descendant_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_closure fk_network_closure_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_closure
    ADD CONSTRAINT fk_network_closure_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: network_edges fk_network_edges_child_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_edges
    ADD CONSTRAINT fk_network_edges_child_agent_id_agent_profiles FOREIGN KEY (child_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_edges fk_network_edges_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_edges
    ADD CONSTRAINT fk_network_edges_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: network_edges fk_network_edges_parent_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_edges
    ADD CONSTRAINT fk_network_edges_parent_agent_id_agent_profiles FOREIGN KEY (parent_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_nodes fk_network_nodes_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_nodes
    ADD CONSTRAINT fk_network_nodes_agent_id_agent_profiles FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_nodes fk_network_nodes_direct_parent_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_nodes
    ADD CONSTRAINT fk_network_nodes_direct_parent_agent_id_agent_profiles FOREIGN KEY (direct_parent_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_nodes fk_network_nodes_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_nodes
    ADD CONSTRAINT fk_network_nodes_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: network_snapshot_nodes fk_network_snapshot_nodes_ancestor_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshot_nodes
    ADD CONSTRAINT fk_network_snapshot_nodes_ancestor_agent_id_agent_profiles FOREIGN KEY (ancestor_agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: network_snapshot_nodes fk_network_snapshot_nodes_rank_id_at_snapshot_ranks; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshot_nodes
    ADD CONSTRAINT fk_network_snapshot_nodes_rank_id_at_snapshot_ranks FOREIGN KEY (rank_id_at_snapshot) REFERENCES public.ranks(id);


--
-- Name: network_snapshot_nodes fk_network_snapshot_nodes_snapshot_id_network_snapshots; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshot_nodes
    ADD CONSTRAINT fk_network_snapshot_nodes_snapshot_id_network_snapshots FOREIGN KEY (snapshot_id) REFERENCES public.network_snapshots(id);


--
-- Name: network_snapshots fk_network_snapshots_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.network_snapshots
    ADD CONSTRAINT fk_network_snapshots_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: notifications fk_notifications_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT fk_notifications_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: notifications fk_notifications_recipient_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT fk_notifications_recipient_user_id_users FOREIGN KEY (recipient_user_id) REFERENCES public.users(id);


--
-- Name: orders fk_orders_cancelled_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_cancelled_by_user_id_users FOREIGN KEY (cancelled_by_user_id) REFERENCES public.users(id);


--
-- Name: orders fk_orders_created_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_created_by_user_id_users FOREIGN KEY (created_by_user_id) REFERENCES public.users(id);


--
-- Name: orders fk_orders_credit_debit_transaction_id_wallet_transactions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_credit_debit_transaction_id_wallet_transactions FOREIGN KEY (credit_debit_transaction_id) REFERENCES public.wallet_transactions(id);


--
-- Name: orders fk_orders_customer_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_customer_user_id_users FOREIGN KEY (customer_user_id) REFERENCES public.users(id);


--
-- Name: orders fk_orders_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: orders fk_orders_paid_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_paid_by_user_id_users FOREIGN KEY (paid_by_user_id) REFERENCES public.users(id);


--
-- Name: orders fk_orders_product_version_id_product_versions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_product_version_id_product_versions FOREIGN KEY (product_version_id) REFERENCES public.product_versions(id);


--
-- Name: partners fk_partners_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.partners
    ADD CONSTRAINT fk_partners_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: password_reset_tokens fk_password_reset_tokens_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT fk_password_reset_tokens_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: product_versions fk_product_versions_commission_plan_version_id_commissi_c160; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_versions
    ADD CONSTRAINT fk_product_versions_commission_plan_version_id_commissi_c160 FOREIGN KEY (commission_plan_version_id) REFERENCES public.commission_plan_versions(id);


--
-- Name: product_versions fk_product_versions_product_id_products; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_versions
    ADD CONSTRAINT fk_product_versions_product_id_products FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- Name: products fk_products_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT fk_products_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: promoter_codes fk_promoter_codes_agent_id_agent_profiles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promoter_codes
    ADD CONSTRAINT fk_promoter_codes_agent_id_agent_profiles FOREIGN KEY (agent_id) REFERENCES public.agent_profiles(id);


--
-- Name: promoter_codes fk_promoter_codes_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promoter_codes
    ADD CONSTRAINT fk_promoter_codes_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: ranks fk_ranks_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ranks
    ADD CONSTRAINT fk_ranks_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: referral_events fk_referral_events_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_events
    ADD CONSTRAINT fk_referral_events_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: referral_events fk_referral_events_promoter_code_id_promoter_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_events
    ADD CONSTRAINT fk_referral_events_promoter_code_id_promoter_codes FOREIGN KEY (promoter_code_id) REFERENCES public.promoter_codes(id);


--
-- Name: referral_sessions fk_referral_sessions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_sessions
    ADD CONSTRAINT fk_referral_sessions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: referral_sessions fk_referral_sessions_promoter_code_id_promoter_codes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_sessions
    ADD CONSTRAINT fk_referral_sessions_promoter_code_id_promoter_codes FOREIGN KEY (promoter_code_id) REFERENCES public.promoter_codes(id);


--
-- Name: role_permissions fk_role_permissions_permission_id_permissions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT fk_role_permissions_permission_id_permissions FOREIGN KEY (permission_id) REFERENCES public.permissions(id);


--
-- Name: role_permissions fk_role_permissions_role_id_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT fk_role_permissions_role_id_roles FOREIGN KEY (role_id) REFERENCES public.roles(id);


--
-- Name: roles fk_roles_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT fk_roles_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: sessions fk_sessions_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT fk_sessions_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: supply_points fk_supply_points_customer_id_customers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supply_points
    ADD CONSTRAINT fk_supply_points_customer_id_customers FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: supply_points fk_supply_points_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supply_points
    ADD CONSTRAINT fk_supply_points_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: supply_points fk_supply_points_supply_address_id_addresses; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.supply_points
    ADD CONSTRAINT fk_supply_points_supply_address_id_addresses FOREIGN KEY (supply_address_id) REFERENCES public.addresses(id);


--
-- Name: ticket_messages fk_ticket_messages_author_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_messages
    ADD CONSTRAINT fk_ticket_messages_author_user_id_users FOREIGN KEY (author_user_id) REFERENCES public.users(id);


--
-- Name: ticket_messages fk_ticket_messages_ticket_id_tickets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ticket_messages
    ADD CONSTRAINT fk_ticket_messages_ticket_id_tickets FOREIGN KEY (ticket_id) REFERENCES public.tickets(id);


--
-- Name: tickets fk_tickets_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_contract_id_contracts FOREIGN KEY (contract_id) REFERENCES public.contracts(id);


--
-- Name: tickets fk_tickets_opened_by_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_opened_by_user_id_users FOREIGN KEY (opened_by_user_id) REFERENCES public.users(id);


--
-- Name: tickets fk_tickets_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: user_roles fk_user_roles_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT fk_user_roles_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: user_roles fk_user_roles_role_id_roles; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT fk_user_roles_role_id_roles FOREIGN KEY (role_id) REFERENCES public.roles(id);


--
-- Name: user_roles fk_user_roles_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT fk_user_roles_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: users fk_users_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT fk_users_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: wallet_transactions fk_wallet_transactions_actor_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_actor_user_id_users FOREIGN KEY (actor_user_id) REFERENCES public.users(id);


--
-- Name: wallet_transactions fk_wallet_transactions_from_wallet_id_wallets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_from_wallet_id_wallets FOREIGN KEY (from_wallet_id) REFERENCES public.wallets(id);


--
-- Name: wallet_transactions fk_wallet_transactions_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: wallet_transactions fk_wallet_transactions_reference_contract_id_contracts; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_reference_contract_id_contracts FOREIGN KEY (reference_contract_id) REFERENCES public.contracts(id);


--
-- Name: wallet_transactions fk_wallet_transactions_reference_invoice_redemption_id__3fd7; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_reference_invoice_redemption_id__3fd7 FOREIGN KEY (reference_invoice_redemption_id) REFERENCES public.invoice_redemptions(id);


--
-- Name: wallet_transactions fk_wallet_transactions_reference_order_id_orders; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_reference_order_id_orders FOREIGN KEY (reference_order_id) REFERENCES public.orders(id);


--
-- Name: wallet_transactions fk_wallet_transactions_reverses_transaction_id_wallet_t_a759; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_reverses_transaction_id_wallet_t_a759 FOREIGN KEY (reverses_transaction_id) REFERENCES public.wallet_transactions(id);


--
-- Name: wallet_transactions fk_wallet_transactions_to_wallet_id_wallets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT fk_wallet_transactions_to_wallet_id_wallets FOREIGN KEY (to_wallet_id) REFERENCES public.wallets(id);


--
-- Name: wallets fk_wallets_organization_id_organizations; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT fk_wallets_organization_id_organizations FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: wallets fk_wallets_user_id_users; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT fk_wallets_user_id_users FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict ztagYhvccX6Vijx3SgLf843zw1AEUemTUbDxynRT1Z1QWkI2qOCWlsJNefAVrpY

