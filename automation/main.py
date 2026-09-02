"""Orchestrator: for each configured building —

    1. Parse the bank statement Excel export.
    2. Log into OXS and read the tenant roster for that building.
    3. For every credit (incoming) row: match the payer name to a tenant.
       Matched -> confirm the bank-transfer payment in OXS, then send a
       WhatsApp confirmation. Unmatched/ambiguous -> skip and log; never
       guess which tenant paid.
    4. For every debit (outgoing) row: record it as a building expense in
       OXS (supplier taken from the bank's transaction description).

Run: python -m automation.main buildings.json
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from automation import oxs_client
from automation.bank_parser import parse_bank_details_from_text, parse_bank_statement, split_payments_and_expenses
from automation.config import BuildingConfig, load_settings
from automation.matcher import match_name
from automation.oxs_client import BankTransferDetails, ExpenseDetails
from automation.whatsapp import WhatsAppConfig, send_payment_confirmation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"run_{datetime.now():%Y%m%d_%H%M%S}.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("automation")


def load_buildings(path: str) -> list[BuildingConfig]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [BuildingConfig(**b) for b in data]


def process_building(page, building: BuildingConfig, wa_config: WhatsAppConfig, audit_writer) -> None:
    log.info("=== Building: %s (%s) ===", building.name, building.oxs_building_id)

    transactions = parse_bank_statement(building.bank_statement_path)
    payments, expenses = split_payments_and_expenses(transactions)
    log.info("Parsed %d payment rows, %d expense rows", len(payments), len(expenses))

    tenants = oxs_client.list_building_tenants(page, building.oxs_building_id)
    log.info("Loaded %d tenants from OXS", len(tenants))

    for tx in payments:
        result = match_name(tx.counterparty_name, tenants)
        audit_writer.writerow(
            [
                building.name,
                "payment",
                tx.row_number,
                tx.date,
                tx.counterparty_name,
                tx.credit,
                result.reason,
                result.candidate.name if result.candidate else "",
                result.score,
            ]
        )
        if result.reason != "matched":
            log.warning(
                "Row %d: NOT confirming (%s) — payer '%s', amount %.2f",
                tx.row_number, result.reason, tx.counterparty_name, tx.credit,
            )
            continue

        tenant = result.candidate
        bank_details = parse_bank_details_from_text(tx.purpose)
        details = BankTransferDetails(
            amount=tx.credit,
            payment_date=tx.date,
            transfer_date=tx.value_date,
            bank_number=bank_details["bank_number"],
            branch_number=bank_details["branch_number"],
            account_number=bank_details["account_number"],
            tenant_note=f"תשלום התקבל ואושר אוטומטית ({tx.date:%d/%m/%Y})",
            internal_note=f"מזוהה אוטומטית מתנועת בנק, אסמכתא {tx.reference}",
        )

        try:
            oxs_client.confirm_tenant_payment(page, tenant.extra["apartment_url"], details)
            log.info("Row %d: confirmed payment for %s (%.2f)", tx.row_number, tenant.name, tx.credit)
        except Exception:
            log.exception("Row %d: failed to confirm payment for %s", tx.row_number, tenant.name)
            continue

        contact = oxs_client.get_tenant_contact(page, tenant.extra["apartment_url"])
        if not contact.get("phone"):
            log.warning("Row %d: no phone on file for %s — skipping WhatsApp", tx.row_number, tenant.name)
            continue
        try:
            send_payment_confirmation(
                wa_config,
                contact["phone"],
                template_params=[tenant.name, f"{tx.credit:.2f}", f"{tx.date:%m/%Y}"],
            )
            log.info("Row %d: WhatsApp sent to %s", tx.row_number, tenant.name)
        except Exception:
            log.exception("Row %d: WhatsApp send failed for %s", tx.row_number, tenant.name)

    for tx in expenses:
        supplier_name = (tx.counterparty_name or tx.action_type or "לא ידוע").strip()
        details = ExpenseDetails(
            supplier_name=supplier_name,
            amount=tx.debit,
            description=tx.purpose or tx.details,
            month=tx.date.month,
            year=tx.date.year,
            mark_as_paid=True,
        )
        audit_writer.writerow(
            [building.name, "expense", tx.row_number, tx.date, supplier_name, tx.debit, "recorded", supplier_name, ""]
        )
        try:
            oxs_client.create_expense(page, building.oxs_building_id, details)
            log.info("Row %d: recorded expense for %s (%.2f)", tx.row_number, supplier_name, tx.debit)
        except Exception:
            log.exception("Row %d: failed to record expense for %s", tx.row_number, supplier_name)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m automation.main buildings.json")
        sys.exit(1)

    settings = load_settings()
    wa_config = WhatsAppConfig(
        phone_number_id=settings.whatsapp_phone_number_id,
        access_token=settings.whatsapp_access_token,
        template_name=settings.whatsapp_template_name,
    )
    buildings = load_buildings(sys.argv[1])

    audit_path = f"audit_{datetime.now():%Y%m%d_%H%M%S}.csv"
    with open(audit_path, "w", newline="", encoding="utf-8-sig") as audit_file:
        audit_writer = csv.writer(audit_file)
        audit_writer.writerow(
            ["building", "kind", "row", "date", "counterparty", "amount", "outcome", "matched_to", "score"]
        )

        headless = os.environ.get("OXS_HEADLESS", "true").lower() != "false"
        slow_mo = int(os.environ.get("OXS_SLOW_MO_MS", "0"))

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
            page = browser.new_page()
            oxs_client.login(page, settings.oxs_username, settings.oxs_password)

            for building in buildings:
                process_building(page, building, wa_config, audit_writer)

            browser.close()

    log.info("Done. Audit trail: %s", audit_path)


if __name__ == "__main__":
    main()
