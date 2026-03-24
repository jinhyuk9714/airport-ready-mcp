from departure_ready.catalog import (
    get_supported_domains,
    is_domain_supported,
    normalize_airport_code,
    normalize_terminal_code,
    unsupported_coverage_note,
)


def test_normalize_airport_code_aliases():
    assert normalize_airport_code("인천공항") == "ICN"
    assert normalize_airport_code("김포") == "GMP"
    assert normalize_airport_code("CJU") == "CJU"


def test_normalize_terminal_aliases():
    assert normalize_terminal_code("ICN", "제1여객터미널") == "T1"
    assert normalize_terminal_code("icn", "terminal 2") == "T2"
    assert normalize_terminal_code("GMP", "국내선") == "DOMESTIC"
    assert normalize_terminal_code("CJU", "unknown") is None


def test_support_matrix_helpers_report_supported_and_unsupported_domains():
    assert "parking" in get_supported_domains("GMP")
    assert is_domain_supported("ICN", "shops") is True
    assert is_domain_supported("GMP", "shops") is False

    note = unsupported_coverage_note("GMP", "priority_lane")
    assert "GMP" in note
    assert "priority_lane" in note
