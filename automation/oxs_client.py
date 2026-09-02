"""Playwright automation for OXS (pro.oxs.co.il).

OXS's API is read-only for tenant debts / payment history (see the API-key
guide), so there is no write endpoint to confirm a payment or record an
expense — the only way to do that is to drive the actual web UI, the same
way a person clicks through it. This module encodes the flows observed on
screen: login, reading a building's tenant roster off the collection grid,
confirming a tenant's bank-transfer payment, and creating a building
expense.

IMPORTANT — these selectors are best-effort, built from screenshots of the
real screens (not from live DOM inspection, since this was authored in a
sandbox with no network access to oxs.co.il). Treat the first real run as
a rehearsal: run with `headless=False` and `slow_mo=300` and watch it,
or use `playwright codegen https://pro.oxs.co.il` yourself to record the
exact clicks if a selector below turns out to be wrong, then adjust the
one function that failed. The functions are kept small and independent
for exactly this reason.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from automation.matcher import Candidate

log = logging.getLogger(__name__)

BASE_URL = "https://pro.oxs.co.il"
DEFAULT_TIMEOUT_MS = 15_000


@dataclass(frozen=True)
class BankTransferDetails:
    amount: float
    payment_date: datetime
    transfer_date: datetime | None
    bank_number: str | None = None
    branch_number: str | None = None
    account_number: str | None = None
    tenant_note: str | None = None  # goes out in the confirmation to the tenant
    internal_note: str | None = None  # "הערת תשלום" — internal use only


@dataclass(frozen=True)
class ExpenseDetails:
    supplier_name: str
    amount: float
    expense_type: str | None = None
    month: int | None = None
    year: int | None = None
    description: str | None = None
    notes: str | None = None
    mark_as_paid: bool = False


def login(page: Page, username: str, password: str) -> None:
    """Log into OXS. Verify field selectors on first run — the login page
    itself was never seen during development."""
    page.goto(f"{BASE_URL}/main/", wait_until="domcontentloaded")

    user_field = page.locator(
        "input[type='email'], input[name*='user' i], input[placeholder*='מייל'], "
        "input[placeholder*='משתמש']"
    ).first
    pass_field = page.locator("input[type='password']").first

    user_field.wait_for(timeout=DEFAULT_TIMEOUT_MS)
    user_field.fill(username)
    pass_field.fill(password)

    submit = page.get_by_role("button", name=re.compile("כניסה|התחבר|Login", re.I)).first
    submit.click()

    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT_MS)
    if "login" in page.url.lower():
        raise RuntimeError(
            "Still on a login-looking URL after submit — check credentials "
            "or adjust the field selectors in oxs_client.login()."
        )


def list_building_tenants(page: Page, building_id: str) -> list[Candidate]:
    """Scrape the building's collection grid for (tenant name -> apartment url).

    The grid ("טבלת גבייה") links each tenant's name to their apartment page
    (/main/building/{id}/apartment/{apartment_id}) — we read those links
    rather than depending on exact column positions, since link hrefs are
    far more stable than table layout.
    """
    page.goto(f"{BASE_URL}/main/building/{building_id}/payments-list", wait_until="networkidle")

    links = page.locator("a[href*='/apartment/']")
    count = links.count()
    seen: dict[str, Candidate] = {}
    apt_re = re.compile(r"/apartment/([^/?#]+)")

    for i in range(count):
        link = links.nth(i)
        href = link.get_attribute("href") or ""
        name = (link.inner_text() or "").strip()
        m = apt_re.search(href)
        if not m or not name:
            continue
        apartment_id = m.group(1)
        seen[apartment_id] = Candidate(
            id=apartment_id,
            name=name,
            extra={"apartment_url": f"{BASE_URL}/main/building/{building_id}/apartment/{apartment_id}"},
        )

    if not seen:
        log.warning(
            "No tenant links found on payments-list for building %s — "
            "the grid markup may not use <a href> for names; inspect and adjust.",
            building_id,
        )
    return list(seen.values())


PHONE_RE = re.compile(r"0(5\d|[2-489])[-\s]?\d{7}")


def get_tenant_contact(page: Page, apartment_url: str) -> dict:
    """Scrape phone/email off the apartment page (seen next to "בעל הדירה")."""
    page.goto(apartment_url, wait_until="networkidle")
    text = page.locator("body").inner_text()

    phone_match = PHONE_RE.search(text)
    email_el = page.locator("a[href^='mailto:']").first
    email = None
    if email_el.count() > 0:
        href = email_el.get_attribute("href") or ""
        email = href.replace("mailto:", "").strip()

    return {
        "phone": phone_match.group(0).replace(" ", "").replace("-", "") if phone_match else None,
        "email": email,
    }


def confirm_tenant_payment(
    page: Page,
    apartment_url: str,
    details: BankTransferDetails,
    payment_method_label: str = "העברה בנקאית",
) -> None:
    """Drive the "תשלום העברה בנקאית" flow and click בצע תשלום."""
    page.goto(apartment_url, wait_until="networkidle")
    page.get_by_text("תשלומים", exact=True).first.click()

    page.get_by_text(payment_method_label, exact=True).click()
    page.get_by_role("button", name="המשך לתשלום").click()

    _fill_field_near_label(page, "תאריך התשלום", _fmt_date(details.payment_date))
    if details.transfer_date:
        _fill_field_near_label(page, "מועד ההעברה", _fmt_date(details.transfer_date))
    if details.bank_number:
        _fill_field_near_label(page, "מס' בנק", details.bank_number)
    if details.branch_number:
        _fill_field_near_label(page, "מס' סניף", details.branch_number)
    if details.account_number:
        _fill_field_near_label(page, "מס' חשבון", details.account_number)
    if details.tenant_note:
        _fill_field_near_label(page, "הוספת הערה לאישור תשלום לדייר", details.tenant_note)
    if details.internal_note:
        _fill_field_near_label(page, "הערת תשלום", details.internal_note)

    page.get_by_role("button", name="בצע תשלום").click()
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT_MS)


def create_expense(page: Page, building_id: str, details: ExpenseDetails) -> None:
    """Drive the "יצירת הוצאה חדשה" flow and click המשך."""
    page.goto(f"{BASE_URL}/main/building/{building_id}/AddNewExpenses", wait_until="networkidle")

    _fill_field_near_label(page, "ספק", details.supplier_name)
    _fill_field_near_label(page, "מחיר", str(details.amount))
    if details.expense_type:
        _fill_field_near_label(page, "סוג", details.expense_type)
    if details.description:
        _fill_field_near_label(page, "תיאור", details.description)
    if details.notes:
        _fill_field_near_label(page, "הערות", details.notes)
    if details.month and details.year:
        _fill_field_near_label(page, "תקופת הוצאה", f"{details.month}/{details.year}")
    if details.mark_as_paid:
        page.get_by_text("סמן הוצאות כשולמו").click()

    page.get_by_role("button", name="המשך").click()
    page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT_MS)


def _fmt_date(d: datetime) -> str:
    return d.strftime("%d/%m/%Y")


def _fill_field_near_label(page: Page, label_text: str, value: str) -> None:
    """Best-effort: find an input associated with a Hebrew field label.

    Tries, in order: a real <label>/for association, then the nearest
    input following the label text in the DOM. Raises a clear error rather
    than silently filling the wrong field if neither works — fix the
    strategy for that one field rather than trusting a guess.
    """
    try:
        field = page.get_by_label(label_text, exact=False)
        field.wait_for(timeout=2_000)
        field.fill(value)
        return
    except PlaywrightTimeoutError:
        pass

    label = page.get_by_text(label_text, exact=False).first
    candidate = label.locator(
        "xpath=following::input[1] | following::textarea[1] | following::select[1]"
    ).first
    try:
        candidate.wait_for(timeout=2_000)
        candidate.fill(value)
    except PlaywrightTimeoutError as e:
        raise RuntimeError(
            f"Could not find an input for label '{label_text}' — adjust "
            "_fill_field_near_label() or add a field-specific selector."
        ) from e
