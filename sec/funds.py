# Funds tracked on the 13F page.
#
# SEC identifies every filer by CIK number, not by name -- so each fund needs its
# CIK looked up once. To add a fund:
#   1. Search the name at https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany
#   2. Pick the entity that actually files 13F-HR. Managers often have a dozen
#      registered entities (fund LPs, GPs, old management companies) and only one
#      of them files. Getting this wrong gives you an empty or stale page --
#      e.g. "APPALOOSA MANAGEMENT LP" (CIK 1006438) stopped filing in 2015, while
#      "Appaloosa LP" (CIK 1656456) is the live filer.
#   3. Confirm at https://data.sec.gov/submissions/CIK##########.json that recent
#      13F-HR filings exist, then add an entry below.
#
# Only managers with over $100M in US-listed equities must file 13F. Plenty of
# small, interesting funds are exempt and simply cannot be tracked this way --
# Laughing Water Capital (CIK 1698456), for instance, has never filed one.
#
# Every CIK below was verified to have recent 13F-HR filings.

FUNDS = {
    "broyhill": {
        "name": "Broyhill Asset Management",
        "cik": "1966057",
    },
    "berkshire": {
        "name": "Berkshire Hathaway",
        "cik": "1067983",
    },
    "baupost": {
        "name": "Baupost Group (Seth Klarman)",
        "cik": "1061768",
    },
    "akre": {
        "name": "Akre Capital Management",
        "cik": "1112520",
    },
    "giverny": {
        "name": "Giverny Capital",
        "cik": "1641864",
    },
    "fundsmith": {
        "name": "Fundsmith (Terry Smith)",
        "cik": "1569205",
    },
    "alta_fox": {
        "name": "Alta Fox Capital Management",
        "cik": "1858353",
    },
    "appaloosa": {
        "name": "Appaloosa (David Tepper)",
        "cik": "1656456",
    },
    "dodge_cox": {
        "name": "Dodge & Cox",
        "cik": "200217",
    },
}


def all_funds():
    """Return funds as a list of dicts (key included), sorted by display name."""
    return sorted(
        ({"key": key, **fund} for key, fund in FUNDS.items()),
        key=lambda f: f["name"].lower(),
    )


def get_fund(fund_key):
    """Look up a single fund by key, or None if it isn't tracked."""
    fund = FUNDS.get(fund_key)
    return {"key": fund_key, **fund} if fund else None
