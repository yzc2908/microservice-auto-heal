"""
Microservice Auto-Heal: LLM-powered multi-agent system for automatic code
defect self-healing and safe refactoring.

Architecture:
    1. DiagnosticAgent  — Cross-file root cause analysis via AST + LLM
    2. CodingAgent      — Patch generation with full repository context
    3. ReviewAgent      — Security & code smell audit before merge
"""

__version__ = "1.0.0"
