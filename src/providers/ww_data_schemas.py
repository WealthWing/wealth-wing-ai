from pydantic import BaseModel, Field
from typing import Literal, Optional, TypedDict
from datetime import datetime
from uuid import UUID

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
    transactions: list[TransactionResponse] = []
    has_more: bool = False
    total_pages: int = 0
    total_count: int = 0

    class Config:
        from_attributes = True