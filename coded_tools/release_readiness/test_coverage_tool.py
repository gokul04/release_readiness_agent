"""CodedTool that parses test execution logs / coverage reports and checks them against a threshold."""
import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional
from xml.etree import ElementTree

from neuro_san.interfaces.coded_tool import CodedTool

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 80.0
COVERAGE_FILE_NAMES = ("coverage.xml", "jacoco.xml", "coverage-summary.json")
JUNIT_GLOB = "**/TEST-*.xml"


class TestCoverageTool(CodedTool):
    """Parses coverage.xml / JaCoCo / JUnit reports and checks line coverage against a threshold."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(self.invoke, args, sly_data)

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        repo_path = args.get("repo_path")
        threshold = float(args.get("coverage_threshold") or DEFAULT_THRESHOLD)
        if not repo_path:
            return {"error": "repo_path is required"}

        root = Path(repo_path).expanduser()
        if not root.exists():
            return {"error": f"repo_path '{repo_path}' does not exist on this filesystem"}

        coverage_pct = self._find_coverage_percent(root)
        tests_passed, tests_failed, tests_skipped = self._summarize_junit(root)

        meets_threshold = coverage_pct is not None and coverage_pct >= threshold

        return {
            "coverage_percent": coverage_pct,
            "coverage_threshold": threshold,
            "meets_threshold": meets_threshold,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "tests_skipped": tests_skipped,
        }

    def _find_coverage_percent(self, root: Path) -> Optional[float]:
        for name in COVERAGE_FILE_NAMES:
            for path in root.rglob(name):
                pct = self._parse_coverage_file(path)
                if pct is not None:
                    return pct
        return None

    def _parse_coverage_file(self, path: Path) -> Optional[float]:
        try:
            if path.suffix == ".xml":
                tree = ElementTree.parse(path)
                el = tree.getroot()
                # Cobertura-style <coverage line-rate="0.85" ...>
                line_rate = el.get("line-rate")
                if line_rate is not None:
                    return round(float(line_rate) * 100, 2)
                # JaCoCo-style <counter type="LINE" missed="x" covered="y"/>.
                # JaCoCo emits counters at method/class/package/report scope, in that
                # order, so the report-wide total is the LAST matching direct child of
                # the root <report> element, not the first one found anywhere in the tree.
                for counter in el.findall("counter"):
                    if counter.get("type") == "LINE":
                        missed = int(counter.get("missed", 0))
                        covered = int(counter.get("covered", 0))
                        total = missed + covered
                        if total > 0:
                            return round(covered / total * 100, 2)
            elif path.suffix == ".json":
                import json
                data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                pct = data.get("total", {}).get("lines", {}).get("pct")
                if pct is not None:
                    return float(pct)
        except (ElementTree.ParseError, OSError, ValueError):
            return None
        return None

    def _summarize_junit(self, root: Path):
        passed = failed = skipped = 0
        found_any = False
        for path in root.glob(JUNIT_GLOB):
            found_any = True
            try:
                tree = ElementTree.parse(path)
                el = tree.getroot()
                tests = int(el.get("tests", 0))
                fail = int(el.get("failures", 0)) + int(el.get("errors", 0))
                skip = int(el.get("skipped", 0))
                failed += fail
                skipped += skip
                passed += max(tests - fail - skip, 0)
            except (ElementTree.ParseError, OSError, ValueError):
                continue
        if not found_any:
            return None, None, None
        return passed, failed, skipped
