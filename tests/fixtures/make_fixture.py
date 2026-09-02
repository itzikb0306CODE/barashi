"""Generate a synthetic bank statement fixture matching the real export's
column layout, but with entirely made-up names/amounts/accounts — used
only for tests, never real financial data."""
from datetime import datetime

import openpyxl


def build(path: str) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "גיליון1"

    ws.append([None])
    ws.append([None])
    ws.append(["תנועות בחשבון"])
    ws.append(["מספר חשבון  00-000-000000  תאריך הפקה  01.01.2026  "])
    ws.append(
        [
            "תאריך", "הפעולה", "פרטים", "אסמכתא", "חובה", "זכות",
            "יתרה בש''ח", "תאריך ערך", "לטובת", "עבור",
        ]
    )
    # A clean tenant payment
    ws.append(
        [
            datetime(2026, 1, 5), "זיכוי ממסד", "המבצע: ישראל ישראלי עבור: תשלום ועד",
            111, "", 400, 10400, datetime(2026, 1, 5), "ישראל ישראלי", "תשלום ועד",
        ]
    )
    # A payment whose bank name has extra middle names vs. the OXS roster
    ws.append(
        [
            datetime(2026, 1, 6), "העברה-נייד", "המבצע: כהן דוד משה עבור: שכירות",
            112, "", 350, 10750, datetime(2026, 1, 6), "כהן דוד משה", "12-673-000000",
        ]
    )
    # An ambiguous name (two similarly-named tenants exist in the fixture roster)
    ws.append(
        [
            datetime(2026, 1, 7), "זיכוי", "המבצע: כהן דוד עבור: תשלום",
            113, "", 200, 10950, datetime(2026, 1, 7), "כהן דוד", "תשלום",
        ]
    )
    # An expense (debit) row
    ws.append(
        [
            datetime(2026, 1, 8), "חברת החשמל", None,
            222222, 850.5, "", 10099.5, datetime(2026, 1, 8), None, None,
        ]
    )
    # A check (debit, no counterparty name available)
    ws.append(
        [
            datetime(2026, 1, 9), "שיק", None,
            5001, 300, "", 9799.5, datetime(2026, 1, 9), None, None,
        ]
    )

    wb.save(path)


if __name__ == "__main__":
    build("sample_bank_statement.xlsx")
