import unittest

from core.recommendation_engine import CURRENT_ALLOCATION, generate_allocation_recommendation


class RecommendationEngineTests(unittest.TestCase):
    def test_healthy_healthy_keeps_90_10(self):
        recommendation = generate_allocation_recommendation(
            {
                "NovaBotV2": {"score": 100, "status": "HEALTHY"},
                "NovaBotV2Options": {"score": 95, "status": "HEALTHY"},
            }
        )
        self.assertEqual(recommendation.recommended_allocation["NovaBotV2"], 90)
        self.assertEqual(recommendation.recommended_allocation["NovaBotV2Options"], 10)

    def test_healthy_warning_recommends_95_5(self):
        recommendation = generate_allocation_recommendation(
            {
                "NovaBotV2": {"score": 95, "status": "HEALTHY"},
                "NovaBotV2Options": {"score": 40, "status": "WARNING"},
            }
        )
        self.assertEqual(recommendation.recommended_allocation["NovaBotV2"], 95)
        self.assertEqual(recommendation.recommended_allocation["NovaBotV2Options"], 5)

    def test_novabotv2_healthy_options_unknown_holds_baseline(self):
        recommendation = generate_allocation_recommendation(
            {
                "NovaBotV2": {"score": 95, "status": "HEALTHY"},
                "NovaBotV2Options": {"score": 0, "status": "UNKNOWN"},
            }
        )
        reasons = " ".join(recommendation.recommendation_reason).lower()

        self.assertLessEqual(
            recommendation.recommended_allocation["NovaBotV2"],
            CURRENT_ALLOCATION["NovaBotV2"],
        )
        self.assertLessEqual(
            recommendation.recommended_allocation["NovaBotV2Options"],
            CURRENT_ALLOCATION["NovaBotV2Options"],
        )
        self.assertIn("insufficient data", reasons)
        self.assertIn("baseline", reasons)

    def test_novabotv2_unknown_options_healthy_holds_baseline(self):
        recommendation = generate_allocation_recommendation(
            {
                "NovaBotV2": {"score": 0, "status": "UNKNOWN"},
                "NovaBotV2Options": {"score": 95, "status": "HEALTHY"},
            }
        )
        reasons = " ".join(recommendation.recommendation_reason).lower()

        self.assertLessEqual(
            recommendation.recommended_allocation["NovaBotV2"],
            CURRENT_ALLOCATION["NovaBotV2"],
        )
        self.assertLessEqual(
            recommendation.recommended_allocation["NovaBotV2Options"],
            CURRENT_ALLOCATION["NovaBotV2Options"],
        )
        self.assertIn("insufficient data", reasons)
        self.assertIn("baseline", reasons)

    def test_both_active_bots_unknown_holds_baseline(self):
        recommendation = generate_allocation_recommendation(
            {
                "NovaBotV2": {"score": 0, "status": "UNKNOWN"},
                "NovaBotV2Options": {"score": 0, "status": "UNKNOWN"},
            }
        )
        reasons = " ".join(recommendation.recommendation_reason).lower()

        self.assertLessEqual(
            recommendation.recommended_allocation["NovaBotV2"],
            CURRENT_ALLOCATION["NovaBotV2"],
        )
        self.assertLessEqual(
            recommendation.recommended_allocation["NovaBotV2Options"],
            CURRENT_ALLOCATION["NovaBotV2Options"],
        )
        self.assertIn("insufficient data", reasons)
        self.assertIn("baseline", reasons)

    def test_warning_healthy_recommends_80_20(self):
        recommendation = generate_allocation_recommendation(
            {
                "NovaBotV2": {"score": 50, "status": "WARNING"},
                "NovaBotV2Options": {"score": 90, "status": "HEALTHY"},
            }
        )
        self.assertEqual(recommendation.recommended_allocation["NovaBotV2"], 80)
        self.assertEqual(recommendation.recommended_allocation["NovaBotV2Options"], 20)

    def test_recommendation_total_is_always_100(self):
        cases = [
            {
                "NovaBotV2": {"score": 100, "status": "HEALTHY"},
                "NovaBotV2Options": {"score": 95, "status": "HEALTHY"},
            },
            {
                "NovaBotV2": {"score": 95, "status": "HEALTHY"},
                "NovaBotV2Options": {"score": 40, "status": "WARNING"},
            },
            {
                "NovaBotV2": {"score": 50, "status": "WARNING"},
                "NovaBotV2Options": {"score": 90, "status": "HEALTHY"},
            },
            {
                "NovaBotV2": {"score": 0, "status": "UNKNOWN"},
                "NovaBotV2Options": {"score": 90, "status": "HEALTHY"},
            },
            {
                "NovaBotV2": {"score": 90, "status": "HEALTHY"},
                "NovaBotV2Options": {"score": 0, "status": "UNKNOWN"},
            },
            {
                "NovaBotV2": {"score": 0, "status": "UNKNOWN"},
                "NovaBotV2Options": {"score": 0, "status": "UNKNOWN"},
            },
        ]
        for bot_health in cases:
            recommendation = generate_allocation_recommendation(bot_health)
            self.assertEqual(sum(recommendation.recommended_allocation.values()), 100)

    def test_recommendation_only_no_export(self):
        recommendation = generate_allocation_recommendation(
            {
                "NovaBotV2": {"score": 95, "status": "HEALTHY"},
                "NovaBotV2Options": {"score": 40, "status": "WARNING"},
            }
        )
        self.assertTrue(recommendation.recommendation_only)
        self.assertFalse(recommendation.downstream_export_enabled)
        self.assertEqual(recommendation.current_allocation["NovaBotV2"], 90)
        self.assertEqual(recommendation.current_allocation["NovaBotV2Options"], 10)

    def test_recommendation_ignores_future_market_regime_input(self):
        recommendation = generate_allocation_recommendation(
            {
                "NovaBotV2": {"score": 100, "status": "HEALTHY"},
                "NovaBotV2Options": {"score": 95, "status": "HEALTHY"},
                "MarketRegimeBot": {"score": 0, "status": "UNKNOWN"},
            },
            warnings=("MarketRegimeBot snapshot missing",),
        )
        self.assertEqual(recommendation.recommended_allocation["NovaBotV2"], 90)
        self.assertEqual(recommendation.recommended_allocation["NovaBotV2Options"], 10)
        self.assertEqual(sum(recommendation.recommended_allocation.values()), 100)


if __name__ == "__main__":
    unittest.main()
