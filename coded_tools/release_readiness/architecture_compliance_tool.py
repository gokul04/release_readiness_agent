"""CodedTool that compares a repository's file tree against internal engineering structure guidelines."""
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List

from neuro_san.interfaces.coded_tool import CodedTool

logger = logging.getLogger(__name__)

# Minimal "internal engineering documentation guidelines" baseline for demo purposes.
# In production this would be fetched from Confluence/an engineering handbook repo.
REQUIRED_PATHS = ["README.md", "src", "tests"]
RECOMMENDED_PATHS = ["CHANGELOG.md", ".gitignore", "docs"]
DISALLOWED_TOP_LEVEL = {".DS_Store", "Thumbs.db"}


class ArchitectureComplianceTool(CodedTool):
    """Parses the repository's raw file tree and compares it against engineering structure guidelines."""

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        return await asyncio.to_thread(self.invoke, args, sly_data)

    def invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> Any:
        repo_path = args.get("repo_path")
        if not repo_path:
            return {"error": "repo_path is required"}

        root = Path(repo_path).expanduser()
        if not root.exists():
            return {"error": f"repo_path '{repo_path}' does not exist on this filesystem"}

        top_level = {entry.name for entry in root.iterdir()}

        missing_required: List[str] = [p for p in REQUIRED_PATHS if p not in top_level]
        missing_recommended: List[str] = [p for p in RECOMMENDED_PATHS if p not in top_level]
        disallowed_present: List[str] = sorted(top_level & DISALLOWED_TOP_LEVEL)

        hard_violations = [
            {"severity": "high", "type": "missing_required_path", "path": p} for p in missing_required
        ] + [
            {"severity": "medium", "type": "disallowed_artifact", "path": p} for p in disallowed_present
        ]
        soft_recommendations = [
            {"severity": "low", "type": "missing_recommended_path", "path": p} for p in missing_recommended
        ]

        return {
            "top_level_entries": sorted(top_level),
            "hard_violations": hard_violations,
            "soft_recommendations": soft_recommendations,
            "compliant": len(hard_violations) == 0,
        }
