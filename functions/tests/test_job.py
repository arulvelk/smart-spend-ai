import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "daily_job"))
from job import MAX_CATCHUP_DAYS, days_to_ingest, plan_alerts  # noqa: E402


def test_catch_up_from_last_loaded_day():
    assert days_to_ingest(date(2026, 11, 1), date(2026, 11, 4)) == [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)]


def test_nothing_to_do_when_current():
    assert days_to_ingest(date(2026, 11, 4), date(2026, 11, 4)) == []


def test_catch_up_is_capped():
    days = days_to_ingest(date(2026, 1, 1), date(2026, 11, 4))
    assert len(days) == MAX_CATCHUP_DAYS and days[-1] == date(2026, 11, 4)


def _b(cat, limit, spent):
    return {"category": cat, "monthly_limit": limit, "spend_month_to_date": spent}


def test_alert_types():
    today = date(2026, 11, 10)  # day 10 of 30
    alerts = {a.category: a for a in plan_alerts(
        [_b("Dining", 450, 500), _b("Coffee", 120, 100), _b("Shopping", 350, 200), _b("Groceries", 750, 200)],
        today, set())}
    assert alerts["Dining"].alert_type == "budget_exceeded"
    assert alerts["Coffee"].alert_type == "budget_threshold"
    assert alerts["Shopping"].alert_type == "on_pace_to_exceed"  # 200/10*30 = 600 > 385
    assert "Groceries" not in alerts  # on pace for 600 of 750


def test_no_pace_alerts_in_first_days_and_no_repeats():
    assert plan_alerts([_b("Shopping", 350, 60)], date(2026, 11, 2), set()) == []
    assert plan_alerts([_b("Dining", 450, 500)], date(2026, 11, 20), {("Dining", "budget_exceeded")}) == []


def test_alert_ids_are_stable():
    a = plan_alerts([_b("Dining", 450, 500)], date(2026, 11, 20), set())[0]
    assert a.row("u", date(2026, 11, 1), "t")["alert_id"] == a.row("u", date(2026, 11, 1), "x")["alert_id"]
