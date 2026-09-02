from pathlib import Path

from automation.bank_parser import parse_bank_details_from_text, parse_bank_statement, split_payments_and_expenses

FIXTURE = Path(__file__).parent / "fixtures" / "sample_bank_statement.xlsx"


def test_parses_all_rows():
    transactions = parse_bank_statement(FIXTURE)
    assert len(transactions) == 5


def test_splits_payments_and_expenses():
    transactions = parse_bank_statement(FIXTURE)
    payments, expenses = split_payments_and_expenses(transactions)
    assert len(payments) == 3
    assert len(expenses) == 2
    assert all(p.is_credit for p in payments)
    assert all(e.is_debit for e in expenses)


def test_payment_fields():
    transactions = parse_bank_statement(FIXTURE)
    payments, _ = split_payments_and_expenses(transactions)
    first = payments[0]
    assert first.counterparty_name == "ישראל ישראלי"
    assert first.credit == 400
    assert first.reference == 111


def test_expense_with_no_counterparty_name():
    transactions = parse_bank_statement(FIXTURE)
    _, expenses = split_payments_and_expenses(transactions)
    check = next(e for e in expenses if e.action_type == "שיק")
    assert check.counterparty_name is None
    assert check.debit == 300


def test_parse_bank_details_from_text():
    details = parse_bank_details_from_text("מבנק 018,סניף 001 ,חשבון 221124190")
    assert details == {"bank_number": "018", "branch_number": "001", "account_number": "221124190"}


def test_parse_bank_details_from_text_missing():
    assert parse_bank_details_from_text("תשלום ועד") == {
        "bank_number": None,
        "branch_number": None,
        "account_number": None,
    }
