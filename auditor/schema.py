from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Item(Strict):
    description: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(ge=0, le=1000000, decimal_places=2)


class Receipt(Strict):
    merchant: str = Field(min_length=1, max_length=120)
    date: date
    total: Decimal = Field(gt=0, le=1000000, decimal_places=2)
    currency: Literal["USD", "EUR", "GBP"]
    category: Literal["meals", "transport", "lodging", "alcohol"]
    tax: Decimal = Field(ge=0, le=1000000, decimal_places=2)
    items: list[Item] = Field(min_length=1, max_length=30)


class Expense(Strict):
    id: str = Field(pattern=r"^e\d{2,3}$")
    receipt_id: str | None = Field(default=None, pattern=r"^r\d{2,3}$")
    amount: Decimal = Field(gt=0, le=1000000, decimal_places=2)
    currency: Literal["USD", "EUR", "GBP"]
    category: Literal["meals", "transport", "lodging", "alcohol"]
    justification: str = Field(default="", max_length=500)


class Report(Strict):
    id: str = Field(pattern=r"^report-\d{2}$")
    employee: str
    title: str
    expenses: list[Expense] = Field(min_length=1, max_length=20)


class Flag(Strict):
    rule: str
    lines: list[str]
    severity: Literal["violation", "review"]
    explanation: str
    evidence: dict


class Review(Strict):
    run_id: str
    action: Literal["approve", "reject", "comment"]
    comment: str = Field(default="", max_length=1000)
