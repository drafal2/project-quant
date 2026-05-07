"""Tests for the logging instrumentation across bootstrappers and the setup_logging helper."""

import logging
from datetime import date

import pytest

from logging_config import setup_logging
from market_conventions import BusinessDayConvention, DayCountConvention
from market_structures.rates.bootstrapper import ZeroCurveBootstrapper
from market_structures.rates.quotes import DepositQuote
from schedules.calendars import CalendarType

REF = date(2024, 1, 2)
USD = CalendarType.USD
MF = BusinessDayConvention.MODIFIED_FOLLOWING
ACT360 = DayCountConvention.ACT_360
ACT365 = DayCountConvention.ACT_365_FIXED


def _deposit_bootstrapper():
    q = DepositQuote(
        rate=0.05,
        tenor="3M",
        spot_lag=2,
        calendar=USD,
        business_day_convention=MF,
        day_count_convention=ACT360,
    )
    return ZeroCurveBootstrapper(
        reference_date=REF,
        quotes=[q],
        day_count_convention=ACT365,
    )


class TestBootstrapperLogging:
    def test_info_summary_emitted_on_bootstrap(self, caplog):
        with caplog.at_level(logging.INFO, logger="market_structures.rates.bootstrapper"):
            _deposit_bootstrapper().bootstrap()

        messages = [r.getMessage() for r in caplog.records]
        assert any("Bootstrapping zero curve from 1 quote" in m for m in messages)
        assert any("Bootstrap complete: 1 pillar" in m for m in messages)
        assert any("NR converged in" in m for m in messages)

    def test_no_debug_records_at_info_level(self, caplog):
        with caplog.at_level(logging.INFO, logger="market_structures.rates.bootstrapper"):
            _deposit_bootstrapper().bootstrap()

        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert debug_records == []

    def test_debug_per_iteration_emitted_at_debug_level(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="market_structures.rates.bootstrapper"):
            _deposit_bootstrapper().bootstrap()

        debug_messages = [
            r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG
        ]
        assert any("NR iter=" in m for m in debug_messages)


class TestSetupLogging:
    def test_default_yaml_config_loads(self):
        setup_logging()
        for name in ("market_structures", "credit", "schedules", "database", "scripts"):
            assert logging.getLogger(name).level == logging.INFO

    def test_level_override_applied(self):
        try:
            setup_logging(level="DEBUG")
            assert logging.getLogger("market_structures").level == logging.DEBUG
            assert logging.getLogger("credit").level == logging.DEBUG
        finally:
            setup_logging()

    def test_missing_yaml_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            setup_logging(yaml_path=tmp_path / "nope.yaml")
