"""Tests for the CodingAgent."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.coding_agent import CodingAgent, CodingInput
from src.agents.diagnostic_agent import DiagnosticReport


class TestCodingAgent:
    @pytest.mark.asyncio
    async def test_generate_fix(self):
        mock_llm = MagicMock()
        mock_response = """## Explanation
The null check was missing in the handler.

```diff
@@ -10,6 +10,8 @@
 def handle(req):
+    if req is None:
+        raise ValueError("req cannot be None")
     return process(req.body)
```

```python
def test_handle_null_request():
    with pytest.raises(ValueError):
        handle(None)
```
"""
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            content=mock_response,
            usage=MagicMock(input_tokens=1200, output_tokens=400),
        ))

        diagnosis = DiagnosticReport(
            root_cause="Null pointer in handle()",
            call_chain="handler -> process",
            affected_files=["api.py"],
            confidence="High",
            impact_assessment="Crashes the request pipeline",
            raw_llm_response=mock_response,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "api.py").write_text("def handle(req):\n    return process(req.body)")

            agent = CodingAgent(llm=mock_llm)
            report = await agent.run(CodingInput(
                diagnostic_report=diagnosis,
                workspace_path=root,
            ))

        assert report.status == "success"
        code = report.data["coding_report"]
        assert "handle" in code.fix_patch or "null" in code.explanation.lower()
