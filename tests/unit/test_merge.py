"""Tests for smart merge utilities."""

from src.graph.state import TravelPlan, PlanStep
from src.utils.merge import smart_merge_plan, identify_affected_steps, merge_tool_results


class TestSmartMerge:
    def test_preserves_unaffected_steps(self):
        plan = TravelPlan(
            plan_id="plan-001",
            steps=[
                PlanStep(step_id=1, description="交通查询", agent_type="transport",
                         input_params={}, expected_output="航班和火车"),
                PlanStep(step_id=2, description="天气查询", agent_type="weather",
                         input_params={}, expected_output="天气预报"),
            ],
            constraints={},
            generated_at="",
        )

        # Regenerate only step 2
        regenerated = [
            PlanStep(step_id=2, description="天气查询（更新）", agent_type="weather",
                     input_params={"days": 7}, expected_output="7天预报"),
        ]

        merged = smart_merge_plan(plan, "天气信息不够详细", [2], regenerated)

        assert len(merged["steps"]) == 2
        # Step 1 should be preserved
        assert merged["steps"][0]["description"] == "交通查询"
        # Step 2 should be updated
        assert merged["steps"][1]["description"] == "天气查询（更新）"
        assert merged["steps"][1]["input_params"] == {"days": 7}

    def test_identify_transport_feedback(self):
        plan = TravelPlan(
            plan_id="plan-001",
            steps=[
                PlanStep(step_id=1, description="交通", agent_type="transport",
                         input_params={}, expected_output=""),
                PlanStep(step_id=2, description="酒店", agent_type="hotel",
                         input_params={}, expected_output=""),
            ],
            constraints={},
            generated_at="",
        )

        affected = identify_affected_steps(plan, "机票太贵了，帮我看看火车")
        assert 1 in affected  # transport step should be affected

    def test_identify_hotel_feedback(self):
        plan = TravelPlan(
            plan_id="plan-001",
            steps=[
                PlanStep(step_id=1, description="交通", agent_type="transport",
                         input_params={}, expected_output=""),
                PlanStep(step_id=2, description="酒店", agent_type="hotel",
                         input_params={}, expected_output=""),
            ],
            constraints={},
            generated_at="",
        )

        affected = identify_affected_steps(plan, "酒店太贵了，换个便宜点的民宿")
        assert 2 in affected

    def test_merge_tool_results_replace(self):
        preserved = {
            1: {"step_id": 1, "data": "original transport", "complete": True},
            2: {"step_id": 2, "data": "original weather", "complete": True},
        }
        new_results = [
            {"step_id": 2, "data": "updated weather", "complete": True},
        ]

        merged = merge_tool_results(preserved, new_results)
        assert len(merged) == 2
        assert merged[1]["data"] == "updated weather"

    def test_merge_tool_results_append(self):
        preserved = {1: {"step_id": 1, "data": "old"}}
        new_results = [
            {"step_id": 2, "data": "new"},
        ]

        merged = merge_tool_results(preserved, new_results)
        assert len(merged) == 2
