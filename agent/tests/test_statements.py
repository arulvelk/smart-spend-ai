from datetime import date

from smartspend_agent.statements import StatementRow, parse_csv_rules, statement_ids

CHASE = """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
10/28/2026,10/29/2026,SQ *BLUE BOTTLE COFFEE,Food & Drink,Sale,-6.25,
10/27/2026,10/28/2026,AMZN Mktp US*2K4L7,Shopping,Sale,-42.10,
10/20/2026,10/20/2026,Payment Thank You-Mobile,,Payment,500.00,
"""

AMEX = """Date,Description,Amount
10/05/2026,UBER *TRIP HELP.UBER.COM,18.40
10/06/2026,TRADER JOE S #127,64.12
10/15/2026,ONLINE PAYMENT - THANK YOU,(300.00)
"""

BANK = """Account Name : Everyday Checking
Account Number : XXXXXX0021

Posted Date,Description,Debit,Credit,Balance
2026-10-01,"ONLINE PMT OAKWOOD APTS",2150.00,,3100.22
2026-10-02,ACME CORP PAYROLL,,3850.00,6950.22
2026-10-03,bad row without amount,,,6950.22
"""


def test_chase_style_negative_purchases():
    p = parse_csv_rules(CHASE)
    assert p and p.parser == "csv-rules" and len(p.rows) == 3
    assert (p.rows[0].txn_date, p.rows[0].amount, p.rows[0].direction) == (date(2026, 10, 28), 6.25, "debit")
    assert p.rows[2].direction == "credit"


def test_amex_style_positive_purchases_and_parentheses():
    p = parse_csv_rules(AMEX)
    assert [r.direction for r in p.rows] == ["debit", "debit", "credit"]
    assert p.rows[2].amount == 300.0
    assert any("positive amounts" in w for w in p.warnings)


def test_bank_debit_credit_columns_with_preamble():
    p = parse_csv_rules(BANK)
    assert [(r.description, r.direction, r.amount) for r in p.rows] == [
        ("ONLINE PMT OAKWOOD APTS", "debit", 2150.0), ("ACME CORP PAYROLL", "credit", 3850.0)]
    assert any("Skipped 1" in w for w in p.warnings)


def test_unknown_layout_returns_none():
    assert parse_csv_rules("foo,bar\n1,2\n") is None


def test_statement_ids_are_stable_and_keep_identical_rows_apart():
    rows = [StatementRow(txn_date=date(2026, 10, 3), description="Blue  Bottle", amount=6.25, direction="debit")] * 2
    a = statement_ids("u", "acct", rows)
    assert len(set(a)) == 2
    assert a == statement_ids("u", "acct", rows)
    assert a != statement_ids("u", "other-acct", rows)
    same_text = [StatementRow(txn_date=date(2026, 10, 3), description="BLUE BOTTLE", amount=6.25, direction="debit")]
    assert statement_ids("u", "acct", same_text)[0] == a[0]  # whitespace and case don't create a new id
