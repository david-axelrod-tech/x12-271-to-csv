import csv
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from x12_271_to_csv import detect_delimiters, parse_271, parse_271_to_csv  # noqa: E402

SAMPLE = os.path.join(ROOT, "samples", "sample_271.x12")


def read_sample():
    with open(SAMPLE, encoding="utf-8") as fh:
        return fh.read()


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.patients = parse_271(read_sample())

    def test_one_row_per_patient(self):
        self.assertEqual(len(self.patients), 3)
        self.assertEqual([p["HL_ID"] for p in self.patients], ["3", "4", "5"])

    def test_subscriber_fields(self):
        p = self.patients[0]
        self.assertEqual(p["Last_Name"], "DOE")
        self.assertEqual(p["First_Name"], "JANE")
        self.assertEqual(p["Middle_Initial"], "Q")
        self.assertEqual(p["Member_ID"], "ZZ12345A")
        self.assertEqual(p["DOB"], "1950-06-14")
        self.assertEqual(p["Gender"], "F")
        self.assertEqual(p["Street"], "123 MAPLE ST APT 4")
        self.assertEqual((p["City"], p["State"], p["Zip"]), ("SPRINGDALE", "NY", "12345"))

    def test_dependent_loop_is_its_own_row(self):
        dep = self.patients[2]
        self.assertEqual((dep["First_Name"], dep["Last_Name"]), ("ROBIN", "ROE"))
        self.assertEqual(dep["DOB"], "2015-03-20")
        self.assertIn("LAKESIDE MANAGED CARE", dep["Insurance_Plans"])
        # the dependent's plan must not bleed into the subscriber's row
        self.assertEqual(self.patients[1]["Insurance_Plans"], [])

    def test_managed_care_plan(self):
        p = self.patients[0]
        self.assertEqual(p["Insurance_Plans"], ["HAVENBROOK HEALTH PLAN"])
        self.assertEqual(p["Insurance_Plan_IDs"], ["MCO001"])

    def test_medicaid_message_fields(self):
        p = self.patients[0]
        self.assertEqual(p["County_Code"], "35")
        self.assertEqual(p["Recert_Month"], "0925")
        self.assertEqual(len(p["All_Messages"]), 3)

    def test_eligibility_status_collected(self):
        self.assertEqual(self.patients[0]["Eligibility_Status"], ["MEDICAID", "MEDICAID"])


class DelimiterTests(unittest.TestCase):
    def test_detects_standard_delimiters(self):
        self.assertEqual(detect_delimiters(read_sample()), ("*", "~"))

    def test_non_standard_delimiters(self):
        content = read_sample().replace("*", "|").replace("~", "!")
        self.assertEqual(detect_delimiters(content), ("|", "!"))
        patients = parse_271(content)
        self.assertEqual(len(patients), 3)
        self.assertEqual(patients[0]["Last_Name"], "DOE")

    def test_falls_back_to_defaults(self):
        self.assertEqual(detect_delimiters("GS*HB*X~"), ("*", "~"))


class CsvOutputTests(unittest.TestCase):
    def test_csv_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.csv")
            n = parse_271_to_csv(SAMPLE, out)
            self.assertEqual(n, 3)
            with open(out, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["Eligibility_Status"], "MEDICAID")      # de-duplicated
        self.assertEqual(rows[0]["All_Messages"],
                         "CNTY CD=35; RECERT MONTH=0925; PLAN CODE: 12 EXCESS INCOME")
        self.assertEqual(rows[2]["Insurance_Plan_IDs"], "MCO002")


if __name__ == "__main__":
    unittest.main()
