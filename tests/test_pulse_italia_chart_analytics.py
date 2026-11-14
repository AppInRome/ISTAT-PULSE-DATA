"""PULSE derivation tests, synthetic data only. No source requests or article release."""
import unittest
from scripts.pulse_italia_chart_analytics import calculate


def series(periods, values, unit="%"):
    return {"indicator":"Esempio fittizio", "unit":unit,
            "observations":[{"period":p,"value":v} for p,v in zip(periods,values)]}


def view(result,name):
    return next(x for x in result["views"] if x["id"]==name)


class ChartAnalyticsTests(unittest.TestCase):
    def test_annual_delta_relative_index_and_mean(self):
        x=calculate(series(["2022","2023","2024","2025"],[10,12,15,18]))
        self.assertEqual([p["value"] for p in view(x,"delta")["points"]],
                         [None,2,3,3])
        self.assertEqual(view(x,"delta")["points"][-1]["unit"],"punti percentuali")
        self.assertEqual(view(x,"relative_change")["points"][1]["value"],20)
        self.assertEqual(view(x,"index_100")["points"][-1]["value"],180)
        self.assertEqual(view(x,"rolling_mean_3")["points"][2]["value"],12.333333)
        self.assertTrue(x["no_imputation_or_forecasting"])

    def test_monthly_year_over_year_same_month_not_previous_observation(self):
        x=calculate(series(["2024-01","2025-01","2025-02","2026-01"],[20,25,40,23]))
        annual=view(x,"year_over_year")
        self.assertEqual(annual["points"][1]["value"],5)
        self.assertEqual(annual["points"][3]["value"],-2)
        self.assertEqual(annual["points"][3]["based_on"],["2025-01","2026-01"])
        self.assertIsNone(view(x,"delta")["points"][1]["value"])

    def test_gap_never_interpolates_rolling_average(self):
        x=calculate(series(["2024-01","2024-02","2024-04","2024-05"],[1,2,4,5],"numero"))
        self.assertNotIn("rolling_mean_3",[v["id"] for v in x["views"]])
        self.assertEqual(view(x,"delta")["points"][2]["unavailable_reason"],
                         "non_consecutive_periods")

    def test_zero_denominator_prevents_relative(self):
        x=calculate(series(["2023","2024","2025"],[0,0,3],"numero"))
        self.assertNotIn("index_100",[v["id"] for v in x["views"]])
        # All percentage changes are impossible with a zero previous value.
        # An entirely unavailable graph is suppressed rather than fabricated.
        self.assertNotIn("relative_change",[v["id"] for v in x["views"]])

    def test_quarterly_yoy(self):
        x=calculate(series(["2024-Q1","2024-Q2","2025-Q1","2025-Q2"],
                           [4,5,6,7],"%"))
        self.assertEqual(view(x,"year_over_year")["points"][2]["value"],2)
        self.assertEqual(view(x,"year_over_year")["points"][3]["value"],2)

    def test_two_points_no_fake_moving_average(self):
        x=calculate(series(["2024","2025"],[10,12],"numero"))
        self.assertNotIn("rolling_mean_3",[v["id"] for v in x["views"]])

    def test_invalid_or_duplicate_periods_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate"):
            calculate(series(["2024","2024"],[1,2]))
        with self.assertRaisesRegex(ValueError,"mixed_calendar"):
            calculate(series(["2024","2024-01"],[1,2]))
        with self.assertRaisesRegex(ValueError,"non_finite"):
            calculate(series(["2024","2025"],[1,"NaN"]))
        with self.assertRaisesRegex(ValueError,"percentage_out"):
            calculate(series(["2024","2025"],[101,102],"%"))

    def test_observations_do_not_change(self):
        s=series(["2023","2024","2025"],[70,75,73])
        orig=[dict(p) for p in s["observations"]]
        calculate(s)
        self.assertEqual(s["observations"],orig)


if __name__=="__main__":
    unittest.main()
