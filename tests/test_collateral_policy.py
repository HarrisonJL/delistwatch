"""
Direct Mode tests for CollateralPolicy.

Direct Mode can't simulate cross-contract calls without a "glsim" hook (the
same documented limitation as this account's earlier consumers,
TreasuryPolicy, ListingGate and RetainerConsumer), so borrow()'s read of
DelistWatch.is_tradeable() is proven live instead - an allowed loan and
refused ones, all linked in CONTRACT.md. What's tested here is everything
that runs before that call.
"""

import pytest

DW_ADDRESS = "0x" + "33" * 20  # never actually called in these tests


def _deploy(direct_vm, direct_deploy, owner, max_age=3600, ltv_bps=5000):
    direct_vm.sender = owner
    return direct_deploy("contracts/collateral_policy.py", DW_ADDRESS, max_age, ltv_bps)


def test_config_and_empty_state(direct_vm, direct_deploy, direct_owner):
    cp = _deploy(direct_vm, direct_deploy, direct_owner)
    cfg = cp.get_config()
    assert cfg["max_age_seconds"] == 3600 and cfg["ltv_bps"] == 5000 and cfg["loan_count"] == 0
    assert cfg["delistwatch_address"].lower() == DW_ADDRESS
    assert cp.total_for("kucoin-storj") == 0
    assert cp.get_loans(0, 10) == []


@pytest.mark.parametrize("max_age, ltv_bps", [(0, 5000), (3600, 0), (3600, 10001)])
def test_invalid_configuration_is_rejected(direct_vm, direct_deploy, direct_owner, max_age, ltv_bps):
    with pytest.raises(Exception):
        _deploy(direct_vm, direct_deploy, direct_owner, max_age, ltv_bps)


def test_zero_amount_is_rejected_before_any_cross_contract_call(direct_vm, direct_deploy, direct_owner):
    cp = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="amount must be positive"):
        cp.borrow("kucoin-storj", 1000, 0)


def test_loan_above_the_ltv_limit_is_rejected_before_any_cross_contract_call(direct_vm, direct_deploy,
                                                                             direct_owner):
    cp = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="loan-to-value limit"):
        cp.borrow("kucoin-storj", 1000, 501)


def test_borrow_reaches_delistwatch_which_direct_mode_cannot_simulate(direct_vm, direct_deploy, direct_owner,
                                                                       direct_alice):
    # Documented, not silently skipped: a valid borrow() call - exactly at
    # the limit - goes on to gl.get_contract_at(...).view().is_tradeable(...),
    # which needs glsim.
    cp = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    with pytest.raises(Exception) as excinfo:
        cp.borrow("kucoin-storj", 1000, 500)
    assert "loan-to-value" not in str(excinfo.value) and "amount must be" not in str(excinfo.value)
    assert cp.get_config()["loan_count"] == 0
