# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# CollateralPolicy - a minimal consumer of DelistWatch, proving the verdict
# can drive a lending decision on-chain: a loan against a token is only
# recorded if DelistWatch's latest check of that token's market is
# TRADING (no announced end to spot trading) and no older than this
# policy's max_age_seconds, and only up to the policy's loan-to-value ratio.
# Anything else - an announced delisting, a market that isn't trading, an
# undetermined check, no check at all, or a stale one - reverts.
#
# GenVM v0.2.11 conventions (locally tested source of truth);
# contracts/collateral_policy_studio_next.py is the deployed port.
# Header must end in a blank line (real GenVM v0.2.11 requirement).

from genlayer import *
import datetime

MAX_PAGE_LIMIT = 50
BPS = 10000


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise gl.vm.UserError(message)


def _now() -> datetime.datetime:
    return datetime.datetime.fromisoformat(gl.message_raw['datetime'])


@allow_storage
class Loan:
    borrower: Address
    watch_id: str
    collateral_value: u256
    amount: u256
    recorded_at: datetime.datetime


class CollateralPolicy(gl.Contract):
    delistwatch_address: Address
    max_age_seconds: u32
    ltv_bps: u32
    loans: DynArray[Loan]
    totals: TreeMap[str, u256]

    def __init__(self, delistwatch_address: str, max_age_seconds: u32, ltv_bps: u32) -> None:
        _require(max_age_seconds > 0, "max_age_seconds must be positive")
        _require(0 < ltv_bps <= BPS, "ltv_bps must be between 1 and 10000")
        self.delistwatch_address = Address(delistwatch_address)
        self.max_age_seconds = max_age_seconds
        self.ltv_bps = ltv_bps

    # Any borrower; the collateral's market must be verified tradeable.
    @gl.public.write
    def borrow(self, watch_id: str, collateral_value: u256, amount: u256) -> None:
        _require(amount > 0, "amount must be positive")
        _require(amount * BPS <= collateral_value * self.ltv_bps,
                 f"amount exceeds the {self.ltv_bps / 100:g}% loan-to-value limit")
        watch = gl.get_contract_at(self.delistwatch_address)
        tradeable = watch.view().is_tradeable(watch_id, self.max_age_seconds)
        _require(tradeable, f"collateral {watch_id!r} refused: DelistWatch has no fresh check showing its spot "
                            f"market trading with no announced delisting")

        loan = self.loans.append_new_get()
        loan.borrower = gl.message.sender_address
        loan.watch_id = watch_id
        loan.collateral_value = collateral_value
        loan.amount = amount
        loan.recorded_at = _now()
        self.totals[watch_id] = u256(self.totals.get(watch_id, u256(0)) + amount)

    @gl.public.view
    def total_for(self, watch_id: str) -> int:
        return self.totals.get(watch_id, u256(0))

    @gl.public.view
    def get_loans(self, offset: u32, limit: u32) -> list:
        limit = min(limit, MAX_PAGE_LIMIT)
        out = []
        i = len(self.loans) - 1 - offset
        while i >= 0 and len(out) < limit:
            loan = self.loans[i]
            out.append({"borrower": loan.borrower.as_hex, "watch_id": loan.watch_id,
                        "collateral_value": loan.collateral_value, "amount": loan.amount,
                        "recorded_at": loan.recorded_at.isoformat()})
            i -= 1
        return out

    @gl.public.view
    def get_config(self) -> dict:
        return {"delistwatch_address": self.delistwatch_address.as_hex, "max_age_seconds": self.max_age_seconds,
                "ltv_bps": self.ltv_bps, "loan_count": len(self.loans)}
