"""Regenerate sec/filers.csv -- the searchable list of every fund that files 13F.

Not imported by the app. Run it by hand every few months to pick up new filers;
fund names and CIKs are stable, so a stale index just means a brand-new fund is
missing for a quarter.

SEC publishes a "Form 13F Data Sets" ZIP each quarter containing every filing made
in a roughly three-month window. Filer names live in COVERPAGE.tsv and CIKs in
SUBMISSION.tsv, joined on accession number.

Usage:
    1. Open https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
    2. Copy the URL of the newest ZIP (named like 01mar2026-31may2026_form13f.zip)
    3. python sec/build_filer_index.py <url-or-local-zip-path>

The ZIP is ~100MB (mostly the holdings table, which we don't need) but the index
it produces is only a few hundred KB.
"""

import csv
import io
import os
import sys
import urllib.request
import zipfile

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "filers.csv")
USER_AGENT = os.environ.get("SEC_USER_AGENT", "")


def load_zip(source):
    if source.startswith("http"):
        if not USER_AGENT:
            sys.exit("Set SEC_USER_AGENT before downloading from SEC.")
        print(f"Downloading {source} ...")
        request = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=180) as response:
            return zipfile.ZipFile(io.BytesIO(response.read()))
    return zipfile.ZipFile(source)


def read_tsv(archive, filename):
    return csv.DictReader(
        io.TextIOWrapper(archive.open(filename), "utf-8", errors="replace"),
        delimiter="\t",
    )


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)

    archive = load_zip(sys.argv[1])

    # Only 13F-HR carries holdings. 13F-NT is a "my holdings are reported by
    # someone else" notice, so those filers have nothing to show.
    submissions = {
        row["ACCESSION_NUMBER"]: row["CIK"]
        for row in read_tsv(archive, "SUBMISSION.tsv")
        if row["SUBMISSIONTYPE"].startswith("13F-HR")
    }

    filers = {}
    for row in read_tsv(archive, "COVERPAGE.tsv"):
        cik = submissions.get(row["ACCESSION_NUMBER"])
        if cik:
            filers[cik.lstrip("0")] = row["FILINGMANAGER_NAME"].strip()

    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["cik", "name"])
        for cik, name in sorted(filers.items(), key=lambda item: item[1].lower()):
            writer.writerow([cik, name])

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"Wrote {len(filers):,} filers to {OUTPUT_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
