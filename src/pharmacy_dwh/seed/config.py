from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Scale:
    sku: int
    customers: int
    cards: int
    pharmacies: int
    batches_per_sku: int
    purchase_lines: int
    sales: int
    refunds: int


BASE_SCALE = Scale(
    sku=550,
    customers=2_200,
    cards=1_800,
    pharmacies=36,
    batches_per_sku=6,
    purchase_lines=5_400,
    sales=21_000,
    refunds=525,
)

DELTA_SCALE = Scale(
    sku=120,
    customers=300,
    cards=240,
    pharmacies=4,
    batches_per_sku=6,
    purchase_lines=900,
    sales=900,
    refunds=23,
)

DEFAULT_AS_OF = date(2026, 10, 1)


@dataclass(frozen=True)
class Settings:
    seed: int
    delta: bool
    as_of: date
    host: str = "localhost"
    port: int = 5432
    user: str = "pharmacy"
    password: str = "pharmacy"

    @property
    def scale(self) -> Scale:
        return DELTA_SCALE if self.delta else BASE_SCALE

    @property
    def namespace(self) -> str:
        return f"S{self.seed:010d}"

    def dsn(self, service: str) -> str:
        return (
            f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/"
            f"{service}_service_db"
        )

