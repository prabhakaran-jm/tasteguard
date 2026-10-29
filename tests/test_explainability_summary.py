from app.scorer import summarize_explainability


def test_explainability_lists_top_three_drivers():
    text = summarize_explainability(
        {"a": 0.27, "b": 0.26, "c": 0.24, "d": 0.1},
        {"a": "Radiohead", "b": "Aesop", "c": "Norwegian Wood", "d": "Other"},
    )
    assert text is not None
    assert text.startswith("Taste drivers:")
    assert "Radiohead (0.27)" in text
    assert "Aesop (0.26)" in text
    assert "Norwegian Wood (0.24)" in text
    assert "Other" not in text


def test_explainability_single_driver():
    text = summarize_explainability({"a": 0.4}, {"a": "Radiohead"})
    assert text == "Taste drivers: Radiohead (0.40)"
