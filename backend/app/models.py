from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


ReviewStatus = Literal["pending", "confirmed", "rejected", "conflict"]


class Victim(BaseModel):
    victim_id: str = Field(default_factory=lambda: f"V-{uuid4().hex[:8]}")
    name: str
    accounts: list[str] = []
    reported_loss: float = Field(ge=0)


class CaseCreate(BaseModel):
    name: str
    case_number: str
    victims: list[Victim] = []


class CaseRecord(CaseCreate):
    case_id: str = Field(default_factory=lambda: f"CASE-{uuid4().hex[:10].upper()}")
    status: Literal["active", "archived"] = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceLocation(BaseModel):
    source_file_id: str | None = None
    archive_member_path: str | None = None
    page_number: int | None = None
    sheet_name: str | None = None
    table_number: int | None = None
    paragraph_number: int | None = None
    row_number: int | None = None
    region: list[float] | None = None


class TransactionRecord(BaseModel):
    transaction_id: str = Field(default_factory=lambda: f"TX-{uuid4().hex[:12].upper()}")
    transaction_time: datetime
    serial_number: str = ""
    payer_account: str
    payer_name: str
    payer_institution: str = ""
    payer_bank: str = ""
    payee_account: str
    payee_name: str
    payee_institution: str = ""
    payee_bank: str = ""
    debit_credit: str = "借"
    currency: str = "CNY"
    amount: float = Field(gt=0)
    balance_after: float | None = None
    channel: str = ""
    summary: str = ""
    region: str = ""
    transaction_type: str = "转账"
    source: SourceLocation = Field(default_factory=SourceLocation)
    parser_name: str = "manual"
    model_id: str | None = None
    prompt_version: str | None = None
    confidence: dict[str, float] = {}
    review_status: ReviewStatus = "pending"
    review_note: str = ""
    duplicate_group: str | None = None
    conflict_status: str | None = None
    provenance: Literal["original", "human_confirmed", "rule_computed", "model_suggested"] = "model_suggested"

    @field_validator("transaction_time", mode="after")
    @classmethod
    def normalize_business_time(cls, value: datetime) -> datetime:
        # Source statements describe a local business time. Vision/text models
        # sometimes append Z even when the source contains no timezone; retain
        # the displayed wall-clock value and normalize all records consistently.
        return value.replace(tzinfo=None)

    @field_validator("payer_account", "payee_account")
    @classmethod
    def clean_account(cls, value: str) -> str:
        return "".join(ch for ch in value if ch.isalnum())


class DraftUpdate(BaseModel):
    review_status: ReviewStatus | None = None
    review_note: str | None = None
    payer_account: str | None = None
    payer_name: str | None = None
    payee_account: str | None = None
    payee_name: str | None = None
    amount: float | None = Field(default=None, gt=0)
    summary: str | None = None


class VersionCreate(BaseModel):
    name: str


class VersionRecord(BaseModel):
    version_id: str
    name: str
    created_at: datetime
    record_count: int
    sha256: str
    csv_path: str


class SeedCreate(BaseModel):
    victim_id: str
    transaction_id: str
    amount: float = Field(gt=0)
    confirmed_by: str = "办案人员"


class SeedRecord(SeedCreate):
    seed_id: str = Field(default_factory=lambda: f"SEED-{uuid4().hex[:10]}")
    confirmed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AttributionEdge(BaseModel):
    transaction_id: str
    from_account: str
    to_account: str
    original_amount: float
    attributed_amount: float


class AttributionResult(BaseModel):
    method: Literal["fifo", "conservative", "possible_max", "proportional"]
    total_attributed: float
    remaining_amount: float
    edges: list[AttributionEdge]
    is_inference: bool = True
    disclaimer: str = "本结果为资金研判推定，不代表银行原始事实或司法认定。"
