"""Placeholder rank ladder -- see docs/open-questions.md #1. Personal tokens increase
monotonically by design so the entrepreneurial-difference test cases are meaningful.

personal_volume_threshold_cents / group_volume_threshold_cents are placeholder
promotion-progress figures added alongside migration 0010 -- see
docs/business-rules.md#rank-promotion-progress-placeholder. Not confirmed Lial
Energy policy; both are cumulative ("lifetime") totals, not evaluated over any
rolling window."""

RULE_VERSION = "2026.1-placeholder"

RANK_SEED = [
    {"code": "S1", "name": "Seller 1", "level": 1, "personal_token_cents": 4000, "personal_volume_threshold_cents": 0, "group_volume_threshold_cents": 0},
    {"code": "S2", "name": "Seller 2", "level": 2, "personal_token_cents": 4500, "personal_volume_threshold_cents": 1500, "group_volume_threshold_cents": 1500},
    {"code": "S3", "name": "Seller 3", "level": 3, "personal_token_cents": 5000, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 4000},
    {"code": "TL1", "name": "Team Leader 1", "level": 4, "personal_token_cents": 5500, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 8000},
    {"code": "TL2", "name": "Team Leader 2", "level": 5, "personal_token_cents": 6000, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 12000},
    {"code": "TL3", "name": "Team Leader 3", "level": 6, "personal_token_cents": 6500, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 16000},
    {"code": "TL4", "name": "Team Leader 4", "level": 7, "personal_token_cents": 7000, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 20000},
    {"code": "MD1", "name": "Manager Director 1", "level": 8, "personal_token_cents": 7500, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 25000},
    {"code": "MD2", "name": "Manager Director 2", "level": 9, "personal_token_cents": 8000, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 30000},
    {"code": "MD3", "name": "Manager Director 3", "level": 10, "personal_token_cents": 8500, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 35000},
    {"code": "MD4", "name": "Manager Director 4", "level": 11, "personal_token_cents": 9000, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 40000},
    {"code": "MD5", "name": "Manager Director 5", "level": 12, "personal_token_cents": 9500, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 45000},
]
