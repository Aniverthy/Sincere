"""GST invoicing tests (FR-6.5).

FR-6.5 (DECIDED): place of supply comes from the billing address, is **backend bookkeeping
only**, and has **zero effect on queue/matching**. The last clause gets a structural test at
the bottom of this file.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from sincere.monetization.gst import (
    HOME_STATE_CODE,
    compute,
    financial_year_for,
    invoice_number,
    is_valid_state,
)

RATE = 0.18


class TestPlaceOfSupply:
    """Intra-state supplies split CGST/SGST; inter-state charge a single IGST."""

    def test_home_state_splits_cgst_sgst(self) -> None:
        breakdown = compute(gross_paise=79_900, place_of_supply_state=HOME_STATE_CODE, rate=RATE)
        assert breakdown.is_interstate is False
        assert breakdown.igst_paise == 0
        assert breakdown.cgst_paise > 0 and breakdown.sgst_paise > 0

    def test_other_state_charges_igst(self) -> None:
        breakdown = compute(gross_paise=79_900, place_of_supply_state="MH", rate=RATE)
        assert breakdown.is_interstate is True
        assert breakdown.cgst_paise == 0 and breakdown.sgst_paise == 0
        assert breakdown.igst_paise > 0

    def test_the_split_does_not_change_what_the_user_pays(self) -> None:
        """The place of supply decides the split, never the total. A user in Mumbai and one
        in Bengaluru pay exactly the same price."""
        home = compute(gross_paise=79_900, place_of_supply_state=HOME_STATE_CODE, rate=RATE)
        away = compute(gross_paise=79_900, place_of_supply_state="MH", rate=RATE)
        assert home.total_paise == away.total_paise == 79_900
        assert home.tax_paise == away.tax_paise

    def test_state_code_is_case_insensitive(self) -> None:
        breakdown = compute(gross_paise=1_000, place_of_supply_state="ka", rate=RATE)
        assert breakdown.is_interstate is False

    def test_valid_state_codes(self) -> None:
        assert is_valid_state("KA") and is_valid_state("mh")
        assert not is_valid_state("XX")
        assert not is_valid_state("")


class TestTaxInclusivePricing:
    """Prices are quoted tax-inclusive, so the taxable value is back-computed."""

    def test_hand_computed_breakdown(self) -> None:
        # ₹499.00 = 49900 paise inclusive of 18% GST.
        # taxable = round(49900 / 1.18) = round(42288.14) = 42288
        # tax     = 49900 - 42288 = 7612
        breakdown = compute(gross_paise=49_900, place_of_supply_state="MH", rate=RATE)
        assert breakdown.taxable_paise == 42_288
        assert breakdown.igst_paise == 7_612
        assert breakdown.total_paise == 49_900

    def test_intra_state_halves_are_exact(self) -> None:
        breakdown = compute(gross_paise=49_900, place_of_supply_state="KA", rate=RATE)
        assert breakdown.cgst_paise + breakdown.sgst_paise == 7_612
        # Odd paisa goes to CGST so the pair still sums exactly.
        assert breakdown.cgst_paise == 3_806
        assert breakdown.sgst_paise == 3_806

    def test_odd_paisa_is_not_lost(self) -> None:
        """An odd tax amount must still split without dropping a paisa."""
        breakdown = compute(gross_paise=101, place_of_supply_state="KA", rate=RATE)
        assert breakdown.cgst_paise + breakdown.sgst_paise == breakdown.tax_paise

    def test_zero_amount_is_safe(self) -> None:
        breakdown = compute(gross_paise=0, place_of_supply_state="KA", rate=RATE)
        assert breakdown.total_paise == 0 and breakdown.tax_paise == 0


class TestInvoiceNumbering:
    def test_format_is_sequential_and_padded(self) -> None:
        assert invoice_number(1, "2026-27") == "SNC/2026-27/000001"
        assert invoice_number(4_321, "2026-27") == "SNC/2026-27/004321"

    def test_financial_year_runs_april_to_march(self) -> None:
        """India's FY starts in April, so March 2027 belongs to FY 2026-27."""
        assert financial_year_for(month=4, year=2026) == "2026-27"
        assert financial_year_for(month=12, year=2026) == "2026-27"
        assert financial_year_for(month=3, year=2027) == "2026-27"
        assert financial_year_for(month=4, year=2027) == "2027-28"


@given(
    gross=st.integers(min_value=0, max_value=10_000_000),
    state=st.sampled_from(["KA", "MH", "DL", "TN", "WB"]),
)
@settings(max_examples=400, deadline=None)
def test_invoice_lines_always_sum_to_the_amount_charged(gross: int, state: str) -> None:
    """The compliance invariant: ``taxable + tax == gross``, exactly, always.

    An invoice whose lines do not sum to the amount charged is not a valid invoice — this is
    the one property that must hold for every price the product could ever quote.
    """
    breakdown = compute(gross_paise=gross, place_of_supply_state=state, rate=RATE)

    assert breakdown.taxable_paise + breakdown.tax_paise == gross
    assert breakdown.total_paise == gross
    assert breakdown.taxable_paise >= 0
    assert breakdown.cgst_paise >= 0 and breakdown.sgst_paise >= 0 and breakdown.igst_paise >= 0
    # Never both an intra-state and an inter-state charge on one invoice.
    assert not (breakdown.igst_paise > 0 and (breakdown.cgst_paise or breakdown.sgst_paise))


def test_gst_never_touches_queue_or_matching() -> None:
    """FR-6.5: "backend bookkeeping only, **zero effect on queue/matching**".

    Structural assertion — the GST module must not import admission or matching, so it has no
    mechanism by which a billing address could influence someone's place in line.
    """
    import ast
    import inspect

    import sincere.monetization.gst as gst_module

    # Parse the imports rather than grep the text — the module docstring legitimately quotes
    # the rule, and a text search would match its own citation of the requirement.
    tree = ast.parse(inspect.getsource(gst_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = {"admission", "matching", "queue"}
    offending = [
        name for name in imported if any(part in name.split(".") for part in forbidden)
    ]
    assert not offending, f"GST must not reach queue or matching logic, found: {offending}"
