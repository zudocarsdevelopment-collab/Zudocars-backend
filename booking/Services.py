"""
therentos_sync/services.py

Logs into theRentOS, fetches the server-rendered Estimates HTML page,
and parses it into a list of plain dicts your React dashboard can consume
as JSON.

theRentOS has NO public list API for estimates (only a per-record
`.../estimates/__ID__/json` detail endpoint), so this module scrapes the
same HTML table your browser renders at:
    https://avs.therentos.com/admin/estimates

IMPORTANT — you must confirm two things against the real site before this
will work, both marked TODO below:
  1. The exact login URL and form field names (email/password/csrf).
  2. Whether theRentOS terms of service permit automated access at all —
     check with them or use an official export/API if one exists.
"""

import re
import time
from dataclasses import dataclass, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.cache import cache

BASE_URL = "https://avs.therentos.com"
LOGIN_URL = f"{BASE_URL}/login"          # TODO: confirm real login URL
ESTIMATES_URL = f"{BASE_URL}/admin/estimates"

SESSION_CACHE_KEY = "therentos_session_cookies"
SESSION_TTL_SECONDS = 60 * 30            # re-login every 30 min to be safe
LIST_CACHE_KEY_TMPL = "therentos_estimates_page_{page}_{filters}"
LIST_CACHE_TTL_SECONDS = 60 * 3          # don't hammer their server


class TheRentOSAuthError(Exception):
    pass


class TheRentOSFetchError(Exception):
    pass


@dataclass
class Estimate:
    estimate_id: str
    customer_name: str
    customer_phone: str
    vehicle_category: str
    vehicle_plate: Optional[str]
    vehicle_year: Optional[str]
    pickup: str
    dropoff: str
    priority: str
    created_by: str
    date_from: str
    date_to: str
    total: str
    status: str
    status_label: str
    payment: str
    created_at: str
    open_url: str
    public_view_url: Optional[str]


def _get_session() -> requests.Session:
    """
    Returns an authenticated requests.Session, reusing cached cookies
    when they're still fresh, otherwise logging in again.
    """
    cached_cookies = cache.get(SESSION_CACHE_KEY)
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "Mozilla/5.0 (compatible; ZudocarsSync/1.0)"}
    )

    if cached_cookies:
        session.cookies.update(cached_cookies)
        # Quick check: does a protected page still render as logged in?
        check = session.get(ESTIMATES_URL, timeout=15, allow_redirects=True)
        if check.status_code == 200 and "login" not in check.url:
            return session
        # Cookies expired / invalid -> fall through and re-login

    _login(session)
    cache.set(SESSION_CACHE_KEY, dict(session.cookies), SESSION_TTL_SECONDS)
    return session


def _login(session: requests.Session) -> None:
    """Fetch the login form and submit its CSRF token with existing cookies."""
    email = getattr(settings, "THERENTOS_EMAIL", None)
    password = getattr(settings, "THERENTOS_PASSWORD", None)
    if not email or not password:
        raise TheRentOSAuthError(
            "Set THERENTOS_EMAIL and THERENTOS_PASSWORD in Django settings "
            "(load them from environment variables, never hard-code)."
        )

    login_page = session.get(LOGIN_URL, timeout=15)
    if login_page.status_code != 200:
        raise TheRentOSAuthError(
            f"Could not load login page ({login_page.status_code}). "
            "Confirm LOGIN_URL is correct."
        )
    soup = BeautifulSoup(login_page.text, "html.parser")
    token_input = soup.find("input", {"name": "_token"})
    if not token_input:
        raise TheRentOSAuthError(
            "Could not find CSRF token on login page. The login form's "
            "field names may differ from what this scraper expects — "
            "inspect the real <form> and update _login()."
        )
    payload = {
        "_token": token_input.get("value"),
        "email": email,
        "password": password,
    }
    resp = session.post(LOGIN_URL, data=payload, timeout=15, allow_redirects=True)
    if resp.status_code != 200 or "login" in resp.url:
        raise TheRentOSAuthError(
            "Login failed — check credentials, field names, and whether "
            "theRentOS requires 2FA (which this scraper does not handle)."
        )

def _clean(text: Optional[str]) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _parse_estimates_html(html: str) -> tuple[list[Estimate], int, int]:
    """
    Parses the Estimates list page HTML into Estimate objects.
    Returns (estimates, total_count, total_pages).
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.est-table")
    if not table:
        raise TheRentOSFetchError(
            "Could not find the estimates table in the response — "
            "the page structure may have changed, or the session is not "
            "actually authenticated (check for a login redirect)."
        )

    rows = table.select("tbody tr[data-estimate-id]")
    estimates: list[Estimate] = []

    for row in rows:
        estimate_id = row.get("data-estimate-id", "")

        cust_name_el = row.select_one(".cust-name")
        phone_el = row.select_one(".phone-cell")
        vehicle_cat_el = row.select_one(".ev2-vehicle-cat")
        vehicle_plate_el = row.select_one(".ev2-vehicle-id")
        vehicle_year_el = row.select_one(".ev2-vehicle-year")

        route_pts = row.select(".route-pt")
        pickup = _clean(route_pts[0].get_text()) if len(route_pts) > 0 else ""
        dropoff = _clean(route_pts[1].get_text()) if len(route_pts) > 1 else ""

        priority_select = row.select_one("select.prio-sel")
        priority = ""
        if priority_select:
            selected_opt = priority_select.select_one("option[selected]")
            priority = _clean(selected_opt.get_text()) if selected_opt else ""

        by_name_el = row.select_one(".by-name")

        dt_cells = row.select("td.dt-cell")
        date_from = _clean(dt_cells[0].get_text()) if len(dt_cells) > 0 else ""
        date_to = _clean(dt_cells[1].get_text()) if len(dt_cells) > 1 else ""
        created_at = _clean(dt_cells[2].get_text()) if len(dt_cells) > 2 else ""

        total_el = row.select_one(".total-main")

        status_el = row.select_one(".status-badge")
        status_label = status_el.get("title", "") if status_el else ""
        status_text = _clean(status_el.get_text()) if status_el else ""

        pay_el = row.select_one(".pay-cell")
        payment = _clean(pay_el.get_text()) if pay_el else ""

        public_view_a = row.select_one('a.est-menu-item[target="_blank"]')

        estimates.append(
            Estimate(
                estimate_id=estimate_id,
                customer_name=_clean(cust_name_el.get_text()) if cust_name_el else "",
                customer_phone=_clean(phone_el.get_text()) if phone_el else "",
                vehicle_category=_clean(vehicle_cat_el.get_text()) if vehicle_cat_el else "",
                vehicle_plate=_clean(vehicle_plate_el.get_text()) if vehicle_plate_el else None,
                vehicle_year=_clean(vehicle_year_el.get_text()) if vehicle_year_el else None,
                pickup=pickup,
                dropoff=dropoff,
                priority=priority,
                created_by=_clean(by_name_el.get_text()) if by_name_el else "",
                date_from=date_from,
                date_to=date_to,
                total=_clean(total_el.get_text()) if total_el else "",
                status=status_text,
                status_label=status_label,
                payment=payment,
                created_at=created_at,
                open_url=f"{BASE_URL}/admin/estimates/{estimate_id}",
                public_view_url=public_view_a.get("href") if public_view_a else None,
            )
        )

    total_match = re.search(r"Total:\s*([\d,]+)", soup.get_text())
    total_count = int(total_match.group(1).replace(",", "")) if total_match else len(estimates)

    page_links = soup.select(".pagination .page-item a.page-link")
    page_numbers = [
        int(a.get_text()) for a in page_links if a.get_text().strip().isdigit()
    ]
    total_pages = max(page_numbers) if page_numbers else 1

    return estimates, total_count, total_pages


def fetch_estimates(
    page: int = 1,
    search: str = "",
    status: str = "",
    priority: str = "",
    force_refresh: bool = False,
) -> dict:
    """
    Public entry point. Returns:
        {
            "results": [ {..estimate..}, ... ],
            "page": 1,
            "total_pages": 72,
            "total_count": 3567,
        }
    Cached for a few minutes per (page, filters) combo to avoid hammering
    theRentOS on every dashboard refresh.
    """
    filters_key = f"s={search}|st={status}|p={priority}"
    cache_key = LIST_CACHE_KEY_TMPL.format(page=page, filters=filters_key)

    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    session = _get_session()

    params = {"page": page}
    if search:
        params["search"] = search
    if status:
        params["status"] = status
    if priority:
        params["estimate_priority"] = priority

    resp = session.get(ESTIMATES_URL, params=params, timeout=20)
    if resp.status_code != 200:
        raise TheRentOSFetchError(f"Estimates page returned {resp.status_code}")
    if "login" in resp.url:
        # Session died mid-request; force one retry with a fresh login.
        cache.delete(SESSION_CACHE_KEY)
        session = _get_session()
        resp = session.get(ESTIMATES_URL, params=params, timeout=20)
        if "login" in resp.url:
            raise TheRentOSAuthError("Still redirected to login after re-auth.")

    estimates, total_count, total_pages = _parse_estimates_html(resp.text)

    result = {
        "results": [asdict(e) for e in estimates],
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "fetched_at": time.time(),
    }
    cache.set(cache_key, result, LIST_CACHE_TTL_SECONDS)
    return result
