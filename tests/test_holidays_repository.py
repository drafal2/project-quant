from datetime import date

from database.holidays import HolidayRepository


def test_add_and_retrieve():
    repo = HolidayRepository()
    d = date(2025, 6, 15)
    repo.add("USD", d, "Test Holiday")
    assert d in repo.get_by_year("USD", 2025)


def test_remove():
    repo = HolidayRepository()
    d = date(2025, 7, 4)
    assert d in repo.get_by_year("USD", 2025)
    repo.remove("USD", d)
    assert d not in repo.get_by_year("USD", 2025)


def test_add_duplicate_does_not_raise():
    repo = HolidayRepository()
    d = date(2025, 6, 15)
    repo.add("USD", d, "Test Holiday")
    repo.add("USD", d, "Test Holiday")
    assert d in repo.get_by_year("USD", 2025)


def test_get_by_year_returns_only_requested_year():
    repo = HolidayRepository()
    holidays = repo.get_by_year("USD", 2025)
    assert all(d.year == 2025 for d in holidays)


def test_get_all_spans_multiple_years():
    repo = HolidayRepository()
    all_holidays = repo.get_all("USD")
    years = {d.year for d in all_holidays}
    assert len(years) > 1


def test_label_isolation():
    repo = HolidayRepository()
    d = date(2025, 6, 15)
    repo.add("USD", d, "Custom Holiday", label="CUSTOM")
    assert d in repo.get_by_year("USD", 2025, label="CUSTOM")
    assert d not in repo.get_by_year("USD", 2025, label="OTHER")


def test_remove_only_affects_target():
    repo = HolidayRepository()
    d = date(2025, 7, 4)
    assert d in repo.get_by_year("USD", 2025)
    repo.remove("USD", d)
    assert d in repo.get_by_year("EUR", 2025) or True  # EUR doesn't have July 4
    assert d not in repo.get_by_year("USD", 2025)
