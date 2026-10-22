"""Tests for the JUnit XML parser.

Each test checks ONE behaviour, and its name says which, so a red test tells you
exactly what broke without reading the code.
"""

from pathlib import Path

import pytest

from ci_triage.junit import JUnitParseError, TestResult, parse_junit

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample() -> dict[str, TestResult]:
    """Parse the main fixture once per test and index results by test name."""
    return {r.name: r for r in parse_junit(FIXTURES / "sample_junit.xml")}


def test_reads_every_testcase(sample):
    assert len(sample) == 4


@pytest.mark.parametrize(
    ("name", "expected_status"),
    [
        ("test_total", "passed"),
        ("test_apply_coupon", "failed"),
        ("test_charge_card", "error"),
        ("test_refund", "skipped"),
    ],
)
def test_detects_each_status(sample, name, expected_status):
    # parametrize = one test function, run once per row: 4 tests for the price of 1.
    assert sample[name].status == expected_status


def test_failure_message_comes_from_message_attribute(sample):
    assert sample["test_apply_coupon"].message == "expected 90.0, got 100.0"


def test_error_message_falls_back_to_element_text(sample):
    assert sample["test_charge_card"].message == (
        "TimeoutError: payment gateway did not respond in 5s"
    )


def test_passed_test_has_no_message(sample):
    assert sample["test_total"].message is None


def test_duration_is_parsed_as_float(sample):
    assert sample["test_apply_coupon"].duration_seconds == pytest.approx(1.07)


def test_missing_duration_is_none_not_zero(sample):
    assert sample["test_refund"].duration_seconds is None


def test_test_id_combines_classname_and_name(sample):
    assert sample["test_total"].test_id == "checkout.test_cart::test_total"


def test_single_testsuite_root_is_supported():
    results = parse_junit(FIXTURES / "single_suite.xml")
    assert [r.name for r in results] == ["test_small", "test_big"]


def test_malformed_duration_becomes_none():
    results = {r.name: r for r in parse_junit(FIXTURES / "single_suite.xml")}
    assert results["test_big"].duration_seconds is None


def test_invalid_xml_raises_clear_error(tmp_path):
    bad = tmp_path / "broken.xml"
    bad.write_text("<testsuites><testcase>")  # never closed
    with pytest.raises(JUnitParseError, match="not valid XML"):
        parse_junit(bad)


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(JUnitParseError, match="could not read"):
        parse_junit(tmp_path / "does_not_exist.xml")


def test_non_junit_xml_is_rejected(tmp_path):
    other = tmp_path / "other.xml"
    other.write_text("<library><book/></library>")
    with pytest.raises(JUnitParseError, match="not a JUnit report"):
        parse_junit(other)


def test_results_are_read_only(sample):
    # frozen=True: parsed results are facts about the past and can't be edited.
    with pytest.raises(AttributeError):
        sample["test_total"].status = "failed"


def test_kafka_retry_records_both_attempts():
    # Run the code being tested: parse the real Kafka file
    results = parse_junit(FIXTURES / "kafka_flaky_retry.xml")

    # The file has 2 <testcase> entries, so we expect 2 results
    assert len(results) == 2

    # Give the two results names so the next lines are easy to read
    first, second = results

    # Both entries should be the SAME test (that's what makes it a retry)
    assert first.test_id == second.test_id

    # Attempt 1 failed, attempt 2 passed → this is the flaky pattern
    assert first.status == "failed"
    assert second.status == "passed"

    # The failure message should be the real one from the file
    assert "idle connection" in first.message


def test_test_id_without_classname_is_just_the_name(tmp_path):
    # Create a tiny report where the test has NO classname
    report = tmp_path / "report.xml"
    report.write_text('<testsuite><testcase name="test_login"/></testsuite>')

    # Run the parser on it
    results = parse_junit(report)

    # With no classname, test_id should be just the name
    assert results[0].test_id == "test_login"
