"""CodedTool that scans a repository tree for hardcoded secrets."""
import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from neuro_san.interfaces.coded_tool import CodedTool

logger = logging.getLogger(__name__)

# (finding label, regex) pairs. Intentionally broad heuristics, not a replacement
# for a dedicated secret-scanning service (e.g. gitleaks, truffleHog).
SECRET_PATTERNS = [
    ("AWS Access Key ID", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Generic API Key", re.compile(r"(?i)api[_-]?key['\"]?\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]")),
    ("Hardcoded Password", re.compile(r"(?i)password['\"]?\s*[:=]\s*['\"]([^'\"]{4,})['\"]")),
    ("Private Key Block", re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY-----")),
    ("Slack Token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("Generic Bearer Token", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}")),
]

# Quoted values that are schema/field labels (e.g. `COLUMN_PASSWORD = "password"`), not real secrets.
NON_SECRET_PLACEHOLDER_VALUES = {"password", "passwd", "pwd", "secret", "username", "changeme", "placeholder"}

# Directories never worth scanning.
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", "target"}
# Binary/large file types to skip.
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".jar", ".class", ".exe", ".dll", ".lock"}
MAX_FILE_BYTES = 1_000_000


class SecretScannerTool(CodedTool):
    """Recursively scans a repository path for hardcoded secrets using pattern matching."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(self.invoke, args, sly_data)

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        repo_path = args.get("repo_path")
        if not repo_path:
            return {"error": "repo_path is required"}

        root = Path(repo_path).expanduser()
        if not root.exists():
            return {"error": f"repo_path '{repo_path}' does not exist on this filesystem"}

        findings: List[Dict[str, Any]] = []
        files_scanned = 0

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue
            if file_path.suffix.lower() in SKIP_SUFFIXES:
                continue
            try:
                if file_path.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            files_scanned += 1
            for line_no, line in enumerate(text.splitlines(), start=1):
                for label, pattern in SECRET_PATTERNS:
                    match = pattern.search(line)
                    if not match:
                        continue
                    if label == "Hardcoded Password" and match.group(1).strip().lower() in NON_SECRET_PLACEHOLDER_VALUES:
                        continue
                    findings.append({
                        "severity": "critical" if "Private Key" in label or "AWS" in label else "high",
                        "rule": label,
                        "file": str(file_path.relative_to(root)),
                        "line": line_no,
                    })

        return {
            "files_scanned": files_scanned,
            "findings_count": len(findings),
            "findings": findings,
            "owasp_category": "A02:2021 - Cryptographic Failures / A07:2021 - Identification and Authentication Failures",
        }

