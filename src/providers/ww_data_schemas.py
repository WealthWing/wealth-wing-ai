from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
from uuid import UUID


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
