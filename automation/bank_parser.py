"""Parse bank transaction Excel exports into structured transactions.

Expects the row layout used by the bank's "תנועות בחשבון" (account
transactions) export: a couple of title/metadata rows, a header row, then
one row per transaction. Header columns (Hebrew):

    תאריך | הפעולה | פרטים | אסמכתא | חובה | זכות | יתרה בש"ח |
    תאריך ערך | לטובת | עבור

חובה (debit) rows are money leaving the account (expenses: checks, standing
orders, utility payments...). זכות (credit) rows are money coming in
(mostly tenant payments). לטובת / עבור are pre-split "counterparty name" /
"purpose" columns this bank's export already provides.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import openpyxl

_BANK_DETAILS_RE = re.compile(
    r"מבנק\s*(?P<bank>\d+)\s*,?\s*סניף\s*(?P<branch>\d+)\s*,?\s*חשבון\s*(?P<account>\d+)"
)

HEADER_MARKERS = ("תאריך", "הפעולה")


@dataclass(frozen=True)
class BankTransaction:
    date: datetime
    action_type: str
    details: str | None
    reference: str | int | None
    debit: float
    credit: float
    balance: float | None
    value_date: datetime | None
    counterparty_name: str | None
    purpose: str | None
    row_number: int

    @property
    def is_credit(self) -> bool:
        """Money coming in — a candidate tenant payment."""
        return self.credit > 0

    @property
    def is_debit(self) -> bool:
        """Money going out — a candidate expense."""
        return self.debit > 0

    @property
    def amount(self) -> float:
        return self.credit if self.is_credit else self.debit


def _to_float(value) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _find_header_row(rows: list[tuple]) -> int:
    for i, row in enumerate(rows):
        cells = [str(c).strip() for c in row if c is not None]
        if all(marker in cells for marker in HEADER_MARKERS):
            return i
    raise ValueError(
        f"Could not find header row (looking for {HEADER_MARKERS}); "
        "the bank export format may have changed."
    )


def parse_bank_statement(path: str | Path, sheet_name: str | None = None) -> list[BankTransaction]:
    """Parse a bank statement .xlsx export into a list of BankTransaction."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet_name] if sheet_name else wb.worksheets[0]

    rows = list(ws.iter_rows(values_only=True))
    header_idx = _find_header_row(rows)
    header = [str(c).strip() if c is not None else "" for c in rows[header_idx]]

    def col(name: str) -> int:
        return header.index(name)

    idx = {
        "date": col("תאריך"),
        "action": col("הפעולה"),
        "details": col("פרטים"),
        "reference": col("אסמכתא"),
        "debit": col("חובה"),
        "credit": col("זכות"),
        "balance": col("יתרה בש''ח") if "יתרה בש''ח" in header else col("יתרה בש\"ח"),
        "value_date": col("תאריך ערך"),
        "payee": col("לטובת"),
        "purpose": col("עבור"),
    }

    transactions: list[BankTransaction] = []
    for row_number, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        date = row[idx["date"]]
        if not isinstance(date, datetime):
            continue  # skip blank / trailing rows

        transactions.append(
            BankTransaction(
                date=date,
                action_type=(row[idx["action"]] or "").strip() if row[idx["action"]] else "",
                details=row[idx["details"]],
                reference=row[idx["reference"]],
                debit=_to_float(row[idx["debit"]]),
                credit=_to_float(row[idx["credit"]]),
                balance=row[idx["balance"]],
                value_date=row[idx["value_date"]],
                counterparty_name=row[idx["payee"]],
                purpose=row[idx["purpose"]],
                row_number=row_number,
            )
        )

    return transactions


def parse_bank_details_from_text(purpose: str | None) -> dict:
    """Extract bank/branch/account from an "עבור" note like
    'מבנק 018,סניף 001 ,חשבון 221124190', when present."""
    if not purpose:
        return {"bank_number": None, "branch_number": None, "account_number": None}
    m = _BANK_DETAILS_RE.search(purpose)
    if not m:
        return {"bank_number": None, "branch_number": None, "account_number": None}
    return {
        "bank_number": m.group("bank"),
        "branch_number": m.group("branch"),
        "account_number": m.group("account"),
    }


def split_payments_and_expenses(
    transactions: list[BankTransaction],
) -> tuple[list[BankTransaction], list[BankTransaction]]:
    """Return (candidate tenant payments, candidate expenses)."""
    payments = [t for t in transactions if t.is_credit]
    expenses = [t for t in transactions if t.is_debit]
    return payments, expenses
