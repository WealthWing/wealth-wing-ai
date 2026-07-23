import enum
from datetime import date, datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class TransactionsQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)
    sort_by: Literal["amount", "date", "title"] | None = None
    sort_order: Literal["asc", "desc"] = "desc"
    search: str | None = None
    from_date: datetime | None = None
    to_date: datetime | None = None

class TransactionBase(BaseModel):
    category_id: UUID
    account_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    title: str
    amount: int
    description: Optional[str] = None
    date: Optional[datetime] = None
    currency: Optional[str] = "USD"
    type: Optional[str] = "expense"
    subscription_candidate: bool = False
    subscription_id: Optional[UUID] = None


class TransactionResponse(TransactionBase):
    uuid: UUID
    user_id: UUID
    category: Optional[str] = None
    account_name: Optional[str] = None

    class Config:
        from_attributes = True


class TransactionsAllResponse(BaseModel):
    transactions: list[TransactionResponse] = Field(default_factory=list)
    has_more: bool = False
    total_pages: int = 0
    total_count: int = 0

    class Config:
        from_attributes = True


class CategorySpendingParams(BaseModel):
    from_date: datetime | None = None
    to_date: datetime | None = None

    @field_validator("from_date", "to_date")
    @classmethod
    def normalize_naive_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class CategorySpendingResponse(BaseModel):
    category_id: UUID
    category: str
    expense: int


class CashFlowHistoryRequest(BaseModel):
    from_date: date
    to_date: date
    category_ids: list[UUID] | None = None
    account_ids: list[UUID] | None = None
    project_ids: list[UUID] | None = None
    granularity: Literal["day", "week", "month"] = "month"

    @model_validator(mode="after")
    def validate_date_range(self) -> "CashFlowHistoryRequest":
        if self.from_date > self.to_date:
            raise ValueError("from_date cannot be after to_date")
        return self


class CashFlowPeriodResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    income: int
    expense: int
    refunds: int
    net: int
    transaction_count: int


class CashFlowHistoryResponse(BaseModel):
    timezone: str
    from_date: date
    to_date: date
    granularity: Literal["day", "week", "month"]
    periods: list[CashFlowPeriodResponse]


class AccountTypeEnum(enum.Enum):
    CREDIT_CARD = "CREDIT_CARD"
    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    CASH = "CASH"
    INVESTMENT = "INVESTMENT"
    LOAN = "LOAN"
    OTHER = "OTHER"


class TransactionsAllRequest(BaseModel):
    category_ids: list[UUID] | None = Field(
        default=None,
        description=(
            "Category UUIDs explicitly provided or resolved from trusted data; "
            "never infer UUIDs from category names."
        ),
    )
    category_names: list[str] | None = Field(
        default=None,
        description="Category names explicitly requested by the user.",
    )
    account_ids: list[UUID] | None = Field(
        default=None,
        description=(
            "Account UUIDs explicitly provided or resolved from trusted data; "
            "never infer UUIDs from account names."
        ),
    )
    account_names: list[str] | None = Field(
        default=None,
        description="Account names explicitly requested by the user.",
    )
    merchant_search: str | None = Field(
        default=None,
        description="Merchant name text explicitly requested by the user.",
    )
    transaction_types: list[str] | None = Field(
        default=None,
        description="Transaction types explicitly requested by the user.",
    )
    minimum_amount_cents: int | None = Field(
        default=None,
        ge=0,
        description="Minimum transaction amount magnitude in cents.",
    )
    maximum_amount_cents: int | None = Field(
        default=None,
        ge=0,
        description="Maximum transaction amount magnitude in cents.",
    )
    account_type: AccountTypeEnum | None = Field(
        default=None,
        description="Account type explicitly requested by the user.",
    )

    @model_validator(mode="after")
    def validate_amount_range(self) -> "TransactionsAllRequest":
        if (
            self.minimum_amount_cents is not None
            and self.maximum_amount_cents is not None
            and self.minimum_amount_cents > self.maximum_amount_cents
        ):
            raise ValueError(
                "minimum_amount_cents cannot exceed maximum_amount_cents"
            )
        return self


class TransactionSummaryRequest(BaseModel):
    from_date: date
    to_date: date
    account_types: list[AccountTypeEnum] = Field(
        default_factory=lambda: [
            AccountTypeEnum.CHECKING,
            AccountTypeEnum.CREDIT_CARD,
        ],
        min_length=1,
    )

    @field_validator("account_types")
    @classmethod
    def deduplicate_account_types(
        cls, value: list[AccountTypeEnum]
    ) -> list[AccountTypeEnum]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_date_range(self) -> "TransactionSummaryRequest":
        if self.from_date > self.to_date:
            raise ValueError("from_date cannot be after to_date")
        return self


class TransactionSummaryResponse(BaseModel):
    gross_expense: int
    refunds: int
    net_spending: int
    income: int
    net_activity: int
    expense_transaction_count: int
    refund_transaction_count: int
    income_transaction_count: int
    average_expense: float
    average_monthly_spending: float
    from_date: date
    to_date: date
    included_account_types: list[AccountTypeEnum]
