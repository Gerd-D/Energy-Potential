# /root/energy_mvp/core/finance.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class LoanYear:
    year_index: int
    payment: float
    interest: float
    principal: float
    remaining: float


def annuity_payment(principal: float, annual_rate: float, years: int) -> float:
    if years <= 0:
        return 0.0
    if annual_rate <= 0:
        return principal / years
    r = annual_rate
    return principal * (r * (1 + r) ** years) / ((1 + r) ** years - 1)


def loan_schedule(principal: float, annual_rate: float, years_total: int, grace_years: int) -> List[LoanYear]:
    years_total = max(int(years_total), 0)
    grace_years = max(int(grace_years), 0)
    grace_years = min(grace_years, years_total)

    schedule: List[LoanYear] = []
    remaining = float(principal)

    # Grace: interest-only
    for yi in range(grace_years):
        interest = remaining * annual_rate
        payment = interest
        schedule.append(LoanYear(yi, payment, interest, 0.0, remaining))

    amort_years = years_total - grace_years
    payment_ann = annuity_payment(remaining, annual_rate, amort_years)

    for k in range(amort_years):
        yi = grace_years + k
        interest = remaining * annual_rate
        principal_pay = max(payment_ann - interest, 0.0)
        principal_pay = min(principal_pay, remaining)
        remaining -= principal_pay
        schedule.append(LoanYear(yi, payment_ann, interest, principal_pay, remaining))

    return schedule
