from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class SkuVersion:
    valid_from: datetime
    name: str
    category: str
    is_rx: bool


@dataclass(frozen=True)
class SkuData:
    bk: str
    index: int
    base_price: Decimal
    versions: tuple[SkuVersion, ...]

    def at(self, timestamp: datetime) -> SkuVersion:
        return max(
            (v for v in self.versions if v.valid_from <= timestamp),
            key=lambda version: version.valid_from,
        )


@dataclass(frozen=True)
class BatchData:
    bk: str
    sku: str
    received_at: datetime
    expiry_date: date


@dataclass(frozen=True)
class PlannedLine:
    sku: str
    batch_bk: str
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    is_rx: bool
    sku_name: str
    expiry_date: date


@dataclass(frozen=True)
class PlannedReceipt:
    bk: str
    pharmacy_bk: str
    customer_bk: str | None
    cashier_bk: str
    shift_bk: str
    timestamp: datetime
    doc_type: str
    parent_bk: str | None
    prescription_bk: str | None
    lines: tuple[PlannedLine, ...]

    @property
    def total(self) -> Decimal:
        return sum(
            (line.quantity * line.unit_price - line.discount for line in self.lines),
            Decimal("0.00"),
        )


@dataclass
class SeedContext:
    skus: list[SkuData] = field(default_factory=list)
    customers: list[str] = field(default_factory=list)
    pharmacies: list[str] = field(default_factory=list)
    batches: list[BatchData] = field(default_factory=list)
    receipts: list[PlannedReceipt] = field(default_factory=list)

