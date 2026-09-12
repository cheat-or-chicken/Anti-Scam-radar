from script.evaluate import evaluate_file


async def test_synthetic_golden_regression():
    result = await evaluate_file("fixtures/golden.json")
    assert result["count"] == 30
    assert result["dataset_type"] == "synthetic"
    assert result["failures"] == []
