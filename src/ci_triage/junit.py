"""Parse JUnit XML test reports into simple Python objects.

JUnit XML is the de-facto standard report format: pytest (--junitxml), Gradle,
Maven, Jest (with a reporter) and most CI tools can produce it. Each <testcase>
is one test execution; a child element tells us how it ended:

    <testcase classname="pkg.TestCart" name="test_total" time="0.42"/>          passed
    <testcase ...><failure message="expected 3, got 4">...</failure></testcase>  failed
    <testcase ...><error message="TimeoutError">...</error></testcase>           error
    <testcase ...><skipped/></testcase>                                          skipped
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# The only four outcomes we recognise. Literal makes typos like "fialed" visible to tools.
Status = Literal["passed", "failed", "error", "skipped"]

# Order matters: if a runner ever writes more than one child, the most severe wins.
_OUTCOME_TAGS: tuple[tuple[str, Status], ...] = (
    ("failure", "failed"),  # an assertion didn't hold
    ("error", "error"),  # the test crashed (exception, timeout, setup failure)
    ("skipped", "skipped"),  # the test didn't run
)


class JUnitParseError(Exception):
    """Raised when a file can't be read as a JUnit XML report."""


@dataclass(frozen=True)
class TestResult:
    """One test execution from one report.

    frozen=True makes instances read-only: a parsed result is a fact about the
    past, so nothing should be able to change it later by accident.
    """

    # pytest collects any class named Test* as a test class. This tells pytest
    # "I'm a data record, not a test", so it won't try (and warn).
    __test__ = False

    classname: str
    name: str
    status: Status
    # None means "the report didn't say". Using 0.0 instead would be a lie and
    # would quietly drag down average-duration numbers later.
    duration_seconds: float | None
    message: str | None

    @property
    def test_id(self) -> str:
        """Stable identity for 'the same test' across runs: classname + name."""
        return f"{self.classname}::{self.name}" if self.classname else self.name


def parse_junit(path: str | Path) -> list[TestResult]:
    """Read a JUnit XML file and return one TestResult per <testcase>.

    Raises:
        JUnitParseError: the file is missing, isn't valid XML, or isn't a JUnit report.
    """
    path = Path(path)

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        # `from e` keeps the original error attached, so debugging still shows the root cause.
        raise JUnitParseError(f"{path} is not valid XML: {e}") from e
    except OSError as e:  # missing file, no permission, ...
        raise JUnitParseError(f"could not read {path}: {e}") from e

    # Reports are either <testsuites> wrapping several suites, or a single <testsuite>.
    if root.tag not in ("testsuites", "testsuite"):
        raise JUnitParseError(f"{path} is not a JUnit report (root element is <{root.tag}>)")

    # iter() searches every depth, so both layouts (and nested suites) just work.
    return [_parse_testcase(case) for case in root.iter("testcase")]


def _parse_testcase(case: ET.Element) -> TestResult:
    """Turn one <testcase> element into a TestResult. (Leading _ = internal helper.)"""
    status: Status = "passed"
    message: str | None = None

    for tag, outcome in _OUTCOME_TAGS:
        child = case.find(tag)
        if child is not None:  # careful: an Element with no children is "falsy", so test for None
            status = outcome
            message = _message_from(child)
            break

    return TestResult(
        classname=case.get("classname", ""),
        name=case.get("name", ""),
        status=status,
        duration_seconds=_parse_duration(case.get("time")),
        message=message,
    )


def _message_from(el: ET.Element) -> str | None:
    """Prefer the short `message` attribute; fall back to the element's text (stack trace)."""
    text = el.get("message") or (el.text or "").strip()
    return text or None


def _parse_duration(raw: str | None) -> float | None:
    """'0.84' -> 0.84. Missing or malformed -> None (unknown), never a crash."""
    if raw is None:
        return None
    try:
        # Some runners write thousands separators, e.g. "1,234.5".
        return float(raw.replace(",", ""))
    except ValueError:
        return None
