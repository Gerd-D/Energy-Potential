# /root/energy_mvp/core/ev_tco.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Tuple

from .finance import loan_schedule


# -----------------------------
# Datamodels (Single source of truth)
# -----------------------------
@dataclass(frozen=True)
class EvTcoInputs:
    # Meta / Horizon
    project_name: str
    base_year: int
    horizon_years: int

    # Diesel baseline
    hours_per_year: float
    diesel_l_per_h: float
    diesel_total_l_per_year: float
    diesel_price_eur_per_l: float

    # Electric alternative
    electricity_kwh_per_year: float  # Muss hier definiert sein, wenn es in form_values ist!
    electricity_price_eur_per_kwh: float

    # Investment
    invest_eur: float
    subsidy_rate: float
    resale_old_device_eur: float

    # Financing
    loan_interest: float
    loan_years_total: int
    loan_grace_years: int

    # NPV
    discount_rate: float


@dataclass(frozen=True)
class EvTcoSummary:
    npv: float
    total_net_cashflow: float
    avg_yearly_savings: float


@dataclass(frozen=True)
class CashflowYear:
    year: int
    einsparung: float
    annuitaet: float
    cashflow: float


@dataclass(frozen=True)
class LedgerEntry:
    step: str
    year: int
    account: str
    amount: float
    meta: Dict[str, Any]


# -----------------------------
# Core calculation
# -----------------------------
def run_ev_tco(inputs: EvTcoInputs) -> Tuple[EvTcoSummary, List[CashflowYear], List[LedgerEntry]]:
    ledger: List[LedgerEntry] = []

    def post(step: str, year: int, account: str, amount: float, **meta):
        ledger.append(LedgerEntry(step=step, year=year, account=account, amount=float(amount), meta=dict(meta)))

    # --- Baseline diesel ---
    diesel_l = inputs.diesel_total_l_per_year
    if diesel_l <= 0:
        diesel_l = inputs.hours_per_year * inputs.diesel_l_per_h
        post("derive_diesel_l", inputs.base_year, "DERIVED_DIESEL_L_PER_YEAR", diesel_l,
             hours_per_year=inputs.hours_per_year, diesel_l_per_h=inputs.diesel_l_per_h)

    diesel_cost = diesel_l * inputs.diesel_price_eur_per_l
    post("diesel_cost", inputs.base_year, "OPEX_DIESEL", -diesel_cost,
         diesel_l_per_year=diesel_l, diesel_price=inputs.diesel_price_eur_per_l)


    # --- Electric (always derived from diesel) ---
    DIESEL_TO_ELECTRIC_KWH_PER_L = 3.8

    electricity_kwh = diesel_l * DIESEL_TO_ELECTRIC_KWH_PER_L

    post(
        "derive_electricity_kwh",
        inputs.base_year,
        "DERIVED_ELECTRICITY_KWH_PER_YEAR",
        electricity_kwh,
        diesel_l_per_year=diesel_l,
        factor_kwh_per_l=DIESEL_TO_ELECTRIC_KWH_PER_L,
    )

    elec_cost = electricity_kwh * inputs.electricity_price_eur_per_kwh

    post(
        "electricity_cost",
        inputs.base_year,
        "OPEX_ELECTRICITY",
        -elec_cost,
        kwh_per_year=electricity_kwh,
        price=inputs.electricity_price_eur_per_kwh,
    )
    # Savings per year (positive = good)
    yearly_savings = diesel_cost - elec_cost
    post("yearly_savings", inputs.base_year, "SAVINGS", yearly_savings)

    # --- Investment year 0 ---
    subsidy = inputs.invest_eur * inputs.subsidy_rate
    invest_cf = -inputs.invest_eur + subsidy + inputs.resale_old_device_eur

    post("capex", inputs.base_year, "CAPEX", -inputs.invest_eur)
    post("subsidy", inputs.base_year, "SUBSIDY", subsidy, subsidy_rate=inputs.subsidy_rate)
    post("resale_old_device", inputs.base_year, "RESALE_OLD_DEVICE", inputs.resale_old_device_eur)

    # --- Financing schedule (annual payments) ---
    principal_to_finance = max(inputs.invest_eur - subsidy - inputs.resale_old_device_eur, 0.0)
    sched = loan_schedule(
        principal=principal_to_finance,
        annual_rate=inputs.loan_interest,
        years_total=inputs.loan_years_total,
        grace_years=inputs.loan_grace_years,
    )

    payment_by_year: Dict[int, float] = {}
    for ly in sched:
        abs_year = inputs.base_year + 1 + ly.year_index
        payment_by_year[abs_year] = ly.payment
        post("loan_payment", abs_year, "FIN_LOAN_PAYMENT", -ly.payment,
             interest=ly.interest, principal=ly.principal, remaining=ly.remaining)

    # --- Cashflows over horizon ---
    cashflows: List[CashflowYear] = []
    total_net_cf = 0.0

    # year 0
    cashflows.append(CashflowYear(
        year=inputs.base_year,
        einsparung=0.0,
        annuitaet=0.0,
        cashflow=invest_cf,
    ))
    total_net_cf += invest_cf

    # years 1..horizon
    for i in range(1, int(inputs.horizon_years) + 1):
        year = inputs.base_year + i
        ann = float(payment_by_year.get(year, 0.0))
        net_cf = yearly_savings - ann
        cashflows.append(CashflowYear(year=year, einsparung=yearly_savings, annuitaet=ann, cashflow=net_cf))
        total_net_cf += net_cf

    # --- NPV ---
    npv = 0.0
    for idx, cf in enumerate(cashflows):
        t = idx
        if inputs.discount_rate > 0:
            npv += cf.cashflow / ((1 + inputs.discount_rate) ** t)
        else:
            npv += cf.cashflow

    summary = EvTcoSummary(
        npv=float(npv),
        total_net_cashflow=float(total_net_cf),
        avg_yearly_savings=float(yearly_savings),
    )

    post("summary", inputs.base_year, "SUMMARY_NPV", summary.npv, inputs=asdict(inputs))

    return summary, cashflows, ledger
