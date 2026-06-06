import unittest

from core.recommendation_engine import generate_allocation_recommendation


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

    def test_healthy_unknown_recommends_100_0(self):
        recommendation = generate_allocation_recommendation(
            {
                "NovaBotV2": {"score": 95, "status": "HEALTHY"},
                "NovaBotV2Options": {"score": 0, "status": "UNKNOWN"},
            }
        )
        self.assertEqual(recommendation.recommended_allocation["NovaBotV2"], 100)
        self.assertEqual(recommendation.recommended_allocation["NovaBotV2Options"], 0)

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


if __name__ == "__main__":
    unittest.main()
