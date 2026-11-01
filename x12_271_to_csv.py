#!/usr/bin/env python3
"""
x12_271_to_csv.py -- flatten an ANSI X12 271 Eligibility Response into a CSV.

One row per patient (one per HL*..*22 subscriber loop, and one per HL*..*23
dependent loop).  Delimiters are read from the ISA header, so files that use
non-standard separators work without any configuration.

Usage:
    python x12_271_to_csv.py 271_response.x12
    python x12_271_to_csv.py 271_response.x12 -o eligibility.csv

Standard library only.
"""

import argparse
import csv
import os
import sys

CSV_HEADERS = [
    "HL_ID", "Member_ID", "First_Name", "Last_Name", "Middle_Initial",
    "DOB", "Gender", "Street", "City", "State", "Zip",
    "Eligibility_Status", "Insurance_Plans", "Insurance_Plan_IDs",
    "County_Code", "Recert_Month", "All_Messages",
]

# NM1 entity codes that identify the person the loop is about
PATIENT_ENTITIES = {"IL", "03"}          # IL = subscriber, 03 = dependent
PLAN_ENTITIES = {"Y2", "P4", "PR", "PRP", "SEP", "TTP", "X3"}  # managed care / payers


def _new_patient(hl_id):
    return {
        "HL_ID": hl_id,
        "Member_ID": "",
        "First_Name": "",
        "Last_Name": "",
        "Middle_Initial": "",
        "DOB": "",
        "Gender": "",
        "Street": "",
        "City": "",
        "State": "",
        "Zip": "",
        "Eligibility_Status": [],
        "Insurance_Plans": [],
        "Insurance_Plan_IDs": [],
        "County_Code": "",
        "Recert_Month": "",
        "All_Messages": [],
    }


def detect_delimiters(content):
    """Return (element_separator, segment_terminator) from the ISA header,
    falling back to the X12 defaults '*' and '~'."""
    if content.startswith("ISA") and len(content) > 105:
        return content[3], content[105]
    return "*", "~"


def parse_271(content):
    """Parse the text of a 271 file and return a list of patient dicts."""
    element_sep, segment_term = detect_delimiters(content)
    segments = [s.strip() for s in content.split(segment_term) if s.strip()]

    patients = []
    current = None

    for seg in segments:
        parts = [p.strip() for p in seg.split(element_sep)]
        if not parts or not parts[0]:
            continue
        tag = parts[0]

        def el(i):
            return parts[i] if len(parts) > i else ""

        if tag == "HL":
            level = el(3)
            if level in ("22", "23"):          # subscriber or dependent: a new row
                if current:
                    patients.append(current)
                current = _new_patient(el(1))
            elif level in ("20", "21"):        # back up to payer / provider level
                if current:
                    patients.append(current)
                current = None
            continue

        if current is None:
            continue

        if tag == "NM1":
            entity = el(1)
            if entity in PATIENT_ENTITIES:
                current["Last_Name"] = el(3)
                current["First_Name"] = el(4)
                current["Middle_Initial"] = el(5)
                current["Member_ID"] = el(9)
            elif entity in PLAN_ENTITIES:
                if el(3):
                    current["Insurance_Plans"].append(el(3))
                if el(9):
                    current["Insurance_Plan_IDs"].append(el(9))

        elif tag == "N3":
            current["Street"] = f"{el(1)} {el(2)}".strip()

        elif tag == "N4":
            current["City"], current["State"], current["Zip"] = el(1), el(2), el(3)

        elif tag == "DMG":
            dob = el(2)
            current["DOB"] = f"{dob[:4]}-{dob[4:6]}-{dob[6:]}" if len(dob) == 8 else dob
            current["Gender"] = el(3)

        elif tag == "EB":
            if el(5):
                current["Eligibility_Status"].append(el(5))

        elif tag == "MSG":
            text = el(1)
            if text:
                current["All_Messages"].append(text)
                # Fields NY Medicaid (eMedNY) carries as free text in MSG segments
                if "CNTY CD=" in text:
                    current["County_Code"] = text.split("CNTY CD=")[-1].strip()
                elif "RECERT MONTH=" in text:
                    current["Recert_Month"] = text.split("RECERT MONTH=")[-1].strip()

    if current:
        patients.append(current)
    return patients


def _dedupe_join(values):
    return "; ".join(dict.fromkeys(values))


def write_csv(patients, output_path):
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for p in patients:
            row = dict(p)
            row["Eligibility_Status"] = _dedupe_join(p["Eligibility_Status"])
            row["Insurance_Plans"] = _dedupe_join(p["Insurance_Plans"])
            row["Insurance_Plan_IDs"] = _dedupe_join(p["Insurance_Plan_IDs"])
            row["All_Messages"] = "; ".join(p["All_Messages"])
            writer.writerow(row)


def parse_271_to_csv(input_path, output_path="eligibility_report.csv"):
    """Read a 271 file and write the CSV.  Returns the number of patient rows."""
    with open(input_path, "r", encoding="utf-8", errors="ignore") as fh:
        content = fh.read()
    patients = parse_271(content)
    write_csv(patients, output_path)
    return len(patients)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Convert an X12 271 eligibility response to a one-row-per-patient CSV.")
    ap.add_argument("input", help="271 file (any delimiters; read from the ISA header)")
    ap.add_argument("-o", "--output", metavar="CSV",
                    help="output file (default: <input name>.csv next to the input)")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"error: input file '{args.input}' not found", file=sys.stderr)
        return 1
    output = args.output or os.path.splitext(args.input)[0] + ".csv"

    count = parse_271_to_csv(args.input, output)
    print(f"Converted {count} patient record(s) from '{args.input}' to '{output}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
