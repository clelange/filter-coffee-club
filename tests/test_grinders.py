from app.grinders import (
    recognize_grinder_definition,
    round_to_step,
    translate_reference_setting,
)


def test_reference_conversion_rounds_to_the_nearest_supported_step() -> None:
    assert translate_reference_setting(28, "kingrinder_k6") == 90
    assert translate_reference_setting(29, "kingrinder_k6") == 93
    assert translate_reference_setting(33, "kingrinder_k6") == 106
    assert translate_reference_setting(28, "comandante_c40") == 28
    assert translate_reference_setting(28, "custom") is None
    assert round_to_step(2.25, 0.5) == 2.5


def test_legacy_grinder_recognition_is_case_insensitive() -> None:
    assert recognize_grinder_definition(" COMANDANTE ", "c40 Mk4") == "comandante_c40"
    assert recognize_grinder_definition("kingRINDER", "K6") == "kingrinder_k6"
    assert recognize_grinder_definition("Timemore", "Chestnut Nano 3") == "custom"
