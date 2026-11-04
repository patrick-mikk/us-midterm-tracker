import json, os, unittest
from tests.helpers import ROOT, load
from adapters import nc, base
import chambers

FIX = os.path.join(ROOT, "fixtures")


class NCAdapterTests(unittest.TestCase):
    def test_county_fixture_parses(self):
        rows = load(os.path.join(FIX, "nc_2026_results_92.json"))
        units = nc.parse_rows(rows, 92)
        self.assertIn("NC-SEN-2026", units)
        sen = units["NC-SEN-2026"]
        self.assertEqual(sen["name"], "Wake")
        self.assertEqual(sen["fips"], "37183")
        names = {c[0]: c[1] for c in sen["candidates"]}
        self.assertEqual(names["Roy Cooper"], "DEM")
        self.assertEqual(names["Michael Whatley"], "REP")
        self.assertEqual(names["Michael Dublin"], "GRN")
        self.assertEqual(sen["precincts"], 216)
        self.assertTrue(all(k.startswith("NC-H") or k == "NC-SEN-2026" for k in units))
        for u in units.values():
            total = sum(c[2] for c in u["candidates"])
            self.assertEqual(total, sum(u["byType"][t].get(c[0], 0) for c in u["candidates"]
                                        for t in ("early", "electionDay", "mail", "provisional")))

    def test_statewide_fixture_has_fourteen_house_races(self):
        rows = load(os.path.join(FIX, "nc_2026_results_0.json"))
        contests = {nc.contest_to_race(r["cnm"]) for r in rows}
        contests.discard(None)
        house = [c for c in contests if c[1] == "us_house"]
        self.assertEqual(len(house), 14)
        self.assertIn(("NC-SEN-2026", "us_senate", None), contests)

    def test_party_and_name_cleaning(self):
        self.assertEqual(base.norm_party("GRE"), "GRN")
        self.assertEqual(base.norm_party("Democratic"), "DEM")
        self.assertEqual(base.norm_party("UNA"), "IND")
        self.assertEqual(base.clean_name("Jane  Smith (REP)"), "Jane Smith")

    def test_county_numbering(self):
        self.assertEqual(nc.county_fips(1), "37001")
        self.assertEqual(nc.county_fips(100), "37199")
        self.assertEqual(nc.COUNTIES[59], "Mecklenburg")


class ChamberTests(unittest.TestCase):
    def test_senate_adds_to_100(self):
        races = load(os.path.join(ROOT, "data", "races.json"))
        hold = load(os.path.join(ROOT, "data", "holdovers.json"))["holdovers"]
        sen = [r for r in races["races"] if r["office"] == "us_senate"]
        self.assertEqual(len(sen) + sum(hold.values()), 100)
        summaries = [{"id": r["id"], "office": "us_senate", "state": r["state"], "name": r["name"], "status": "no_votes",
                      "candidates": [], "winProbParty": {}, "pctExpected": 0.0, "expected": 0} for r in sen]
        block = chambers.summarise("us_senate", summaries, {}, hold, n_draws=50)
        self.assertEqual(block["secured"]["DEM"] + block["secured"]["REP"] + block["uncalled"], 100)
        self.assertEqual(sum(block["distribution"]["DEM"].values()), 50)

    def test_house_is_435(self):
        races = load(os.path.join(ROOT, "data", "races.json"))
        self.assertEqual(sum(1 for r in races["races"] if r["office"] == "us_house"), 435)
        self.assertEqual(sum(1 for r in races["races"] if r["office"] == "governor"), 36)


if __name__ == "__main__":
    unittest.main()
