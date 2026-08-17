"""Fetch and parse quarterly institutional holdings (SEC Form 13F-HR).

Pure logic module with no Flask imports -- imported by app.py the same way
dcf/dcf_default.py is.

Data comes from SEC's official endpoints, all structured JSON/XML (no HTML
scraping, no text parsing):

  1. data.sec.gov/submissions/CIK##########.json  -> which 13Fs a fund has filed
  2. www.sec.gov/Archives/.../index.json          -> documents inside one filing
  3. .../informationtable.xml                     -> the actual holdings

SEC requires a User-Agent identifying the requester on every request and returns
403 without one. No API key or other auth is involved.

Tickers are not in 13F data -- holdings are identified by CUSIP -- so CUSIPs are
resolved to tickers via OpenFIGI, which is free and needs no key at low volume.
"""

import logging
import time
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FILING_DIR_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"

REQUEST_TIMEOUT = 15

# SEC permits 10 requests/second. A single fund lookup makes about 5 requests, so
# spacing them is nearly free insurance against ever being rate-limited.
MIN_SEC_REQUEST_INTERVAL = 0.15

# Position changes smaller than this are treated as "held" rather than
# added/trimmed, so tiny share-count drift doesn't create noise.
CHANGE_THRESHOLD_PCT = 1.0

# CUSIP -> ticker never changes, so resolved lookups are cached for the life of
# the process. The same ~100 CUSIPs recur every quarter for a given fund.
_ticker_cache = {}

_last_sec_request_at = 0.0


class SecClientError(Exception):
    """Raised when SEC data can't be fetched or parsed. Caught by the route."""


def _throttle():
    global _last_sec_request_at
    elapsed = time.time() - _last_sec_request_at
    if elapsed < MIN_SEC_REQUEST_INTERVAL:
        time.sleep(MIN_SEC_REQUEST_INTERVAL - elapsed)
    _last_sec_request_at = time.time()


def _sec_get(url, user_agent):
    """GET a SEC URL with the required User-Agent. Returns the raw response."""
    if not user_agent:
        raise SecClientError(
            "SEC_USER_AGENT is not set. SEC requires a User-Agent identifying you "
            "(e.g. 'Your Name your@email.com') on every request."
        )

    _throttle()
    try:
        response = requests.get(
            url,
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        raise SecClientError(f"SEC request timed out after {REQUEST_TIMEOUT}s.")
    except requests.RequestException as e:
        raise SecClientError(f"Could not reach SEC: {e}")

    if response.status_code == 403:
        raise SecClientError(
            "SEC rejected the request (403). This usually means SEC_USER_AGENT is "
            "missing or too generic -- it should contain a real name and email."
        )
    if response.status_code == 404:
        raise SecClientError("SEC returned 404 -- check the CIK is correct.")
    if response.status_code != 200:
        raise SecClientError(f"SEC returned HTTP {response.status_code}.")

    return response


# ---------------------------------------------------------------------------
# Filing history
# ---------------------------------------------------------------------------

def fetch_filing_history(cik, user_agent, limit=12):
    """Return the fund's name and its recent 13F filings, newest quarter first.

    Amendments (13F-HR/A) supersede the original filing for the same quarter, so
    only the most recently filed version of each quarter is returned.
    """
    try:
        cik_int = int(str(cik).strip().lstrip("0") or "0")
    except ValueError:
        raise SecClientError(f"Invalid CIK: {cik!r}")

    data = _sec_get(SUBMISSIONS_URL.format(cik=cik_int), user_agent).json()

    # Note: the submissions endpoint calls this "name" -- "entityName" is a field
    # on the separate XBRL companyfacts API and is absent here.
    fund_name = data.get("name") or f"CIK {cik_int}"
    recent = data.get("filings", {}).get("recent", {})

    by_quarter = {}
    for i, form in enumerate(recent.get("form", [])):
        if form not in ("13F-HR", "13F-HR/A"):
            continue
        report_date = recent["reportDate"][i]
        filing_date = recent["filingDate"][i]
        existing = by_quarter.get(report_date)
        if existing is None or filing_date >= existing["filing_date"]:
            by_quarter[report_date] = {
                "form": form,
                "report_date": report_date,
                "filing_date": filing_date,
                "accession": recent["accessionNumber"][i],
                "is_amendment": form.endswith("/A"),
            }

    filings = sorted(by_quarter.values(), key=lambda f: f["report_date"], reverse=True)
    return {"name": fund_name, "cik": str(cik_int), "filings": filings[:limit]}


# ---------------------------------------------------------------------------
# Holdings (the information table)
# ---------------------------------------------------------------------------

def _localname(tag):
    """Strip the XML namespace: '{http://...}infoTable' -> 'infoTable'."""
    return tag.rsplit("}", 1)[-1]


def _child(element, name):
    for child in element:
        if _localname(child.tag) == name:
            return child
    return None


def _child_text(element, name, default=None):
    child = _child(element, name)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _parse_information_table(xml_bytes):
    """Parse an information table into a list of holdings, or None if this XML
    isn't an information table (each filing contains other XML documents too)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    if _localname(root.tag) != "informationTable":
        return None

    rows = []
    for info in root:
        if _localname(info.tag) != "infoTable":
            continue

        amount = _child(info, "shrsOrPrnAmt")
        try:
            value = int(float(_child_text(info, "value", "0")))
            shares = int(float(_child_text(amount, "sshPrnamt", "0"))) if amount is not None else 0
        except (TypeError, ValueError):
            continue

        cusip = (_child_text(info, "cusip") or "").upper().strip()
        if not cusip:
            continue

        rows.append({
            "cusip": cusip,
            "issuer": _child_text(info, "nameOfIssuer", "").strip(),
            "title_of_class": _child_text(info, "titleOfClass", "").strip(),
            # 'SH' = shares, 'PRN' = principal amount for debt
            "share_type": _child_text(amount, "sshPrnamtType", "SH") if amount is not None else "SH",
            "put_call": _child_text(info, "putCall"),
            "value": value,
            "shares": shares,
        })

    return rows


def _aggregate(rows):
    """Collapse repeated rows for the same security into one position.

    A fund with several managers or voting arrangements files one row per
    manager per security, so the raw table can list the same CUSIP many times.
    """
    positions = {}
    for row in rows:
        key = (row["cusip"], row["put_call"])
        existing = positions.get(key)
        if existing is None:
            positions[key] = dict(row)
        else:
            existing["value"] += row["value"]
            existing["shares"] += row["shares"]
    return list(positions.values())


def fetch_holdings(cik, accession, user_agent):
    """Fetch and parse the holdings for one filing, aggregated by security."""
    cik_int = int(str(cik).lstrip("0") or "0")
    accession_plain = accession.replace("-", "")
    directory = FILING_DIR_URL.format(cik=cik_int, accession=accession_plain)

    index = _sec_get(f"{directory}/index.json", user_agent).json()
    items = index.get("directory", {}).get("item", [])

    # The index's own "type" field is unreliable (SEC reports 'text.gif' for every
    # document), so candidates are identified by extension and confirmed by
    # parsing -- the information table is the XML whose root is <informationTable>.
    candidates = [
        item["name"] for item in items
        if item.get("name", "").lower().endswith(".xml")
        and item.get("name", "").lower() != "primary_doc.xml"
    ]

    for filename in candidates:
        parsed = _parse_information_table(_sec_get(f"{directory}/{filename}", user_agent).content)
        if parsed is not None:
            return _aggregate(parsed)

    raise SecClientError(
        f"No information table found in filing {accession}. The filing may be a "
        "holdings-report notice that reports no positions."
    )


# ---------------------------------------------------------------------------
# CUSIP -> ticker
# ---------------------------------------------------------------------------

def _pick_best_figi_match(matches):
    """Choose the US listing, or nothing at all.

    OpenFIGI returns every listing worldwide and the first entry is often not the
    US one -- Philip Morris comes back as '4I1' on Frankfurt before 'PM', and
    Honeywell returns only currency-denominated lines like 'HONGBP'. Accepting
    only exchCode 'US' means an unrecognised security shows its SEC issuer name
    rather than a plausible-looking but wrong ticker, which would be worse: these
    tickers are meant to be pasted into the DCF page.
    """
    us_matches = [m for m in matches if m.get("exchCode") == "US" and m.get("ticker")]
    if not us_matches:
        return None
    for security_type in ("Common Stock", "ADR", "ETP", "REIT", "Mutual Fund"):
        for match in us_matches:
            if match.get("securityType") == security_type:
                return match
    return us_matches[0]


def resolve_tickers(cusips, api_key=None):
    """Map CUSIPs to tickers via OpenFIGI.

    Degrades gracefully: anything that can't be resolved is simply absent from
    the result, and the page falls back to showing the issuer name from SEC.
    """
    unknown = [c for c in dict.fromkeys(cusips) if c not in _ticker_cache]

    # Without a key OpenFIGI allows 25 requests/minute and 10 lookups per request;
    # a key raises that to 100 lookups per request.
    batch_size = 100 if api_key else 10
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key

    for start in range(0, len(unknown), batch_size):
        batch = unknown[start:start + batch_size]
        try:
            response = requests.post(
                OPENFIGI_URL,
                json=[{"idType": "ID_CUSIP", "idValue": c} for c in batch],
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code == 429:
                logger.warning("OpenFIGI rate limit hit; %d CUSIPs left unresolved.",
                               len(unknown) - start)
                break
            if response.status_code != 200:
                logger.warning("OpenFIGI returned HTTP %s; skipping ticker lookup.",
                               response.status_code)
                break
            results = response.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning("OpenFIGI lookup failed: %s", e)
            break

        for cusip, result in zip(batch, results):
            best = _pick_best_figi_match(result.get("data") or [])
            if best and best.get("ticker"):
                _ticker_cache[cusip] = {
                    "ticker": best["ticker"],
                    "exchange": best.get("exchCode"),
                    "figi_name": best.get("name"),
                }

    return {c: _ticker_cache[c] for c in cusips if c in _ticker_cache}


# ---------------------------------------------------------------------------
# Quarter-over-quarter diff
# ---------------------------------------------------------------------------

def diff_holdings(current, previous):
    """Compare two quarters of holdings, matching positions by CUSIP.

    Annotates each current holding with a status (NEW / ADDED / TRIMMED / HELD)
    and returns positions that were sold out of entirely as a separate list.
    """
    previous_by_key = {(h["cusip"], h["put_call"]): h for h in previous or []}

    for holding in current:
        prior = previous_by_key.get((holding["cusip"], holding["put_call"]))
        if prior is None:
            holding["status"] = "NEW"
            holding["share_change_pct"] = None
            holding["prior_shares"] = None
            continue

        holding["prior_shares"] = prior["shares"]
        if prior["shares"] > 0:
            change = 100.0 * (holding["shares"] - prior["shares"]) / prior["shares"]
        else:
            change = 0.0
        holding["share_change_pct"] = round(change, 1)

        if change > CHANGE_THRESHOLD_PCT:
            holding["status"] = "ADDED"
        elif change < -CHANGE_THRESHOLD_PCT:
            holding["status"] = "TRIMMED"
        else:
            holding["status"] = "HELD"

    current_keys = {(h["cusip"], h["put_call"]) for h in current}
    exited = []
    for key, prior in previous_by_key.items():
        if key not in current_keys:
            exited.append({**prior, "status": "EXITED", "share_change_pct": -100.0})
    exited.sort(key=lambda h: -h["value"])

    return exited


# ---------------------------------------------------------------------------
# Top-level entry point used by the route
# ---------------------------------------------------------------------------

def get_fund_snapshot(cik, user_agent, figi_api_key=None):
    """Latest 13F holdings for a fund, diffed against the prior quarter.

    Makes roughly five SEC requests: one submissions lookup, then an index and
    an information table for each of the two most recent quarters.
    """
    history = fetch_filing_history(cik, user_agent, limit=2)
    filings = history["filings"]

    if not filings:
        return {
            "name": history["name"],
            "cik": history["cik"],
            "has_filings": False,
            "holdings": [],
            "exited": [],
        }

    latest = filings[0]
    holdings = fetch_holdings(history["cik"], latest["accession"], user_agent)

    prior = filings[1] if len(filings) > 1 else None
    prior_holdings = []
    if prior:
        try:
            prior_holdings = fetch_holdings(history["cik"], prior["accession"], user_agent)
        except SecClientError as e:
            # A missing prior quarter costs the diff, not the whole page.
            logger.warning("Could not load prior quarter for CIK %s: %s", history["cik"], e)
            prior = None

    if prior:
        exited = diff_holdings(holdings, prior_holdings)
    else:
        # With no prior quarter to compare against, nothing can be called new or
        # added -- leaving status unset is honest, labelling everything NEW isn't.
        exited = []
        for holding in holdings:
            holding["status"] = None
            holding["share_change_pct"] = None
            holding["prior_shares"] = None

    tickers = resolve_tickers(
        [h["cusip"] for h in holdings] + [h["cusip"] for h in exited],
        api_key=figi_api_key,
    )
    total_value = sum(h["value"] for h in holdings)
    for holding in holdings + exited:
        match = tickers.get(holding["cusip"])
        holding["ticker"] = match["ticker"] if match else None
        holding["exchange"] = match["exchange"] if match else None

    for holding in holdings:
        holding["weight_pct"] = round(100.0 * holding["value"] / total_value, 2) if total_value else 0.0
    for holding in exited:
        # An exited position has no weight in the current portfolio; its "value"
        # is what it was worth last quarter.
        holding["weight_pct"] = None

    holdings.sort(key=lambda h: -h["value"])

    return {
        "name": history["name"],
        "cik": history["cik"],
        "has_filings": True,
        "quarter": latest["report_date"],
        "filed": latest["filing_date"],
        "is_amendment": latest["is_amendment"],
        "prior_quarter": prior["report_date"] if prior else None,
        "position_count": len(holdings),
        "total_value": total_value,
        "holdings": holdings,
        "exited": exited,
        "counts": {
            "new": sum(1 for h in holdings if h["status"] == "NEW") if prior else 0,
            "added": sum(1 for h in holdings if h["status"] == "ADDED") if prior else 0,
            "trimmed": sum(1 for h in holdings if h["status"] == "TRIMMED") if prior else 0,
            "exited": len(exited),
        },
    }
