// Mirrors the Pydantic response schemas in apps/api/app/domains/*/schemas.py.
// Kept hand-written for this vertical slice; generating from the OpenAPI schema
// (packages/api-client) is tracked as Phase F follow-up work.

export type ContractRead = {
  id: string;
  customer_id: string;
  supply_point_id: string;
  product_version_id: string;
  status: string;
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

export type BranchMemberRead = {
  agent_id: string;
  depth: number;
};

export type AgentProfileRead = {
  id: string;
  organization_id: string;
  display_name: string;
  promoter_code: string;
  status: string;
  current_rank_id: string | null;
};

export type SimulationStepRead = {
  beneficiary_agent_id: string;
  rank_code: string;
  gross_amount_cents: number;
  movement_type: string;
  explanation: string;
};

