"""Booking lookup against the site's LIS booking API.

The endpoint address is not in this repository - it is read from the untracked
config.local.json. See labelprint/config.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from .config import Config


class BookingError(Exception):
    """Lookup failed, or the sales ID does not exist."""


@dataclass
class Booking:
    salesid: str
    patientname: str
    gender: str
    age_year: int
    age_month: int
    age_day: int
    patientcode: str = ""
    contactpersonid: str = ""
    bookingdate: str = ""
    referreddoctor: str = ""

    @classmethod
    def from_json(cls, row: dict) -> "Booking":
        def num(key: str) -> int:
            try:
                return int(row.get(key) or 0)
            except (TypeError, ValueError):
                return 0

        return cls(
            salesid=str(row.get("salesid") or "").strip(),
            patientname=str(row.get("patientname") or "").strip(),
            gender=str(row.get("gender") or "").strip(),
            age_year=num("agE_YEAR"),
            age_month=num("agE_MONTH"),
            age_day=num("agE_DAY"),
            patientcode=str(row.get("patientcode") or "").strip(),
            contactpersonid=str(row.get("contactpersonid") or "").strip(),
            bookingdate=str(row.get("bookingdate") or "").strip(),
            referreddoctor=str(row.get("referreddoctor") or "").strip(),
        )


SALES_ID_RE = re.compile(r"^[A-Za-z0-9/\-]{3,32}$")


def normalize_sales_id(raw: str) -> str:
    sid = raw.strip().upper()
    if not SALES_ID_RE.match(sid):
        raise BookingError(f"'{raw.strip()}' does not look like a Sales ID.")
    return sid


def fetch(sales_id: str, cfg: Config) -> Booking:
    if not cfg.api_url:
        raise BookingError(
            "The booking server address is not set on this PC. Use "
            "Tools -> Booking server URL, or put \"api_url\" in "
            "config.local.json.")
    sid = normalize_sales_id(sales_id)
    try:
        resp = requests.get(
            cfg.api_url, params={"SalesID": sid}, timeout=cfg.api_timeout_s
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.exceptions.Timeout:
        raise BookingError(f"Server did not respond within {cfg.api_timeout_s:.0f}s.")
    except requests.exceptions.RequestException as exc:
        raise BookingError(f"Could not reach the booking server: {exc}")
    except ValueError:
        raise BookingError("Booking server returned a malformed response.")

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list) or not payload:
        raise BookingError(f"No booking found for {sid}.")

    booking = Booking.from_json(payload[0])
    if not booking.salesid:
        booking.salesid = sid
    if not booking.patientname:
        raise BookingError(f"Booking {sid} has no patient name; refusing to print.")
    return booking
