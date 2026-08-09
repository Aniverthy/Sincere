"""GST invoicing (FR-6.5). Pure functions.

FR-6.5 (DECIDED): "GST invoicing records **place-of-supply (state) from billing address** —
backend bookkeeping only, **zero effect on queue/matching**."

The place-of-supply rule decides the *split*, not the rate: an intra-state supply is charged
as CGST + SGST (half each), an inter-state supply as a single IGST. The total is identical
either way, which is why this is bookkeeping rather than pricing.

Sincère's place of business determines "intra" vs "inter". That is a business fact, not a
user-supplied one, so it lives here as a constant rather than in per-request config.
"""

from __future__ import annotations

from dataclasses import dataclass

#: State code of Sincère's registered place of business. Supplies to this state are intra-state.
HOME_STATE_CODE = "KA"  # Karnataka — the single-city launch (§25 phase 2)

#: GST state codes, for validating a billing address's place of supply.
STATE_CODES: frozenset[str] = frozenset(
    {
        "AN", "AP", "AR", "AS", "BR", "CH", "CT", "DL", "DN", "GA", "GJ", "HP", "HR",
        "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP", "MZ", "NL", "OR",
        "PB", "PY", "RJ", "SK", "TG", "TN", "TR", "UP", "UT", "WB",
    }
)


@dataclass(frozen=True, slots=True)
class GstBreakdown:
    """The tax lines on one invoice. Amounts in paise."""

    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_paise: int
    place_of_supply_state: str
    is_interstate: bool

    @property
    def tax_paise(self) -> int:
        return self.cgst_paise + self.sgst_paise + self.igst_paise


def compute(
    *, gross_paise: int, place_of_supply_state: str, rate: float
) -> GstBreakdown:
    """Split a **tax-inclusive** price into its taxable value and GST components.

    Prices are quoted to users tax-inclusive (₹499 means ₹499 paid), so the taxable value is
    back-computed rather than added on top. Quoting ex-tax and adding GST at checkout would
    change the amount the user agreed to — a consumer-law problem, not just an accounting one.

    Rounding: the tax is rounded to the nearest paisa and the taxable value is whatever
    remains, so ``taxable + tax == gross`` exactly. An invoice whose lines do not sum to the
    amount charged is not a valid invoice.
    """
    state = (place_of_supply_state or "").strip().upper()
    interstate = state != HOME_STATE_CODE

    taxable = round(gross_paise / (1.0 + rate))
    tax = gross_paise - taxable

    if interstate:
        cgst = sgst = 0
        igst = tax
    else:
        # Half each, with any odd paisa going to CGST so the pair still sums to `tax`.
        sgst = tax // 2
        cgst = tax - sgst
        igst = 0

    return GstBreakdown(
        taxable_paise=taxable,
        cgst_paise=cgst,
        sgst_paise=sgst,
        igst_paise=igst,
        total_paise=gross_paise,
        place_of_supply_state=state,
        is_interstate=interstate,
    )


def is_valid_state(code: str) -> bool:
    return (code or "").strip().upper() in STATE_CODES


def invoice_number(sequence: int, financial_year: str) -> str:
    """GST invoice numbers must be sequential and unique within a financial year."""
    return f"SNC/{financial_year}/{sequence:06d}"


def financial_year_for(month: int, year: int) -> str:
    """India's financial year runs April-March, so an invoice in March 2027 belongs to
    FY 2026-27, not 2027-28."""
    start = year if month >= 4 else year - 1
    return f"{start}-{str(start + 1)[-2:]}"
