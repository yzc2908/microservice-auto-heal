"""
Demo script for Microservice Auto-Heal — Multi-Agent Pipeline Simulation.

Run this directly to generate a visual walkthrough of the full
Diagnose → Code → Review → Merge pipeline for screenshots.

Usage:
    python demo.py
    py demo.py
"""

import time
import textwrap


class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    MAGENTA = "\033[95m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    DIM = "\033[2m"


def rule(text: str, color: str = Colors.CYAN) -> None:
    width = 80
    print(f"\n{color}{'=' * width}{Colors.RESET}")
    print(f"{Colors.BOLD}{color}  {text}{Colors.RESET}")
    print(f"{color}{'=' * width}{Colors.RESET}\n")


def step(num: int, title: str) -> None:
    print(f"\n{Colors.BOLD}{Colors.YELLOW}[Step {num}] {title}{Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")


def agent_say(agent: str, msg: str) -> None:
    colors = {
        "Diagnostic": Colors.CYAN,
        "Coding": Colors.GREEN,
        "Review": Colors.MAGENTA,
    }
    c = colors.get(agent, Colors.RESET)
    indent = "    "
    for line in msg.split("\n"):
        print(f"{indent}{c}[{agent}]{Colors.RESET} {line}")
    time.sleep(0.15)


def info(msg: str) -> None:
    print(f"  {Colors.DIM}{msg}{Colors.RESET}")


def main() -> None:
    rule("Microservice Auto-Heal — Multi-Agent Pipeline Demo", Colors.CYAN)
    print(f"  {Colors.DIM}GitHub: https://github.com/yzc2908/microservice-auto-heal{Colors.RESET}")
    print(f"  {Colors.DIM}Model:  Claude Opus 4.7  |  Max Context: 200K tokens{Colors.RESET}")

    # ── Phase 0: Trigger ──
    rule("PHASE 0 — Error Ingestion", Colors.CYAN)
    step(0, "Receiving error from Sentry & CI/CD")

    agent_say("Diagnostic", "Incoming error event received...")
    info("  Source: Sentry Issue #45821")
    info("  Error:  NullReferenceException in PaymentService.validate()")
    info("  CI Job:  unit-tests (GitHub Actions) — FAILED")
    print()

    sentry_event = textwrap.dedent("""\
      ┌─ Sentry Error Event ─────────────────────────────────────┐
      │ Issue ID:  45821                                          │
      │ Title:     NullReferenceException in validate()           │
      │ Culprit:   services/payment.py in PaymentService.validate │
      │ Level:     ERROR                                          │
      │ Timestamp: 2026-05-03T00:25:00Z                           │
      │ Stacktrace:                                               │
      │   app/handler.py:108 in handle_request                    │
      │   services/payment.py:52 in validate                      │
      │   lib/validators.py:31 in check_amount                    │
      └──────────────────────────────────────────────────────────┘""")
    print(f"{Colors.RED}{sentry_event}{Colors.RESET}")

    # ── Phase 1: Diagnosis ──
    rule("PHASE 1 — Diagnostic Agent (Root Cause Analysis)", Colors.CYAN)
    step(1, "Running AST analysis on repository...")

    agent_say("Diagnostic", "Parsing 142 Python files, building cross-file call graph...")
    time.sleep(0.2)
    info("  ✓ AST parsed: 142 files, 1,847 functions, 203 classes")
    info("  ✓ Call chain traced: handle_request → validate → check_amount")

    step(2, "Constructing LLM context prompt (38,000 tokens)...")
    agent_say("Diagnostic", "Sending to Claude Opus 4.7 for deep chain-of-thought reasoning...")
    time.sleep(0.3)

    step(3, "Diagnostic Report generated:")
    diag_output = textwrap.dedent("""\
      ╔══ DIAGNOSTIC REPORT ═══════════════════════════════════════╗
      ║  Root Cause:                                              ║
      ║  In lib/validators.py:31, check_amount() does not handle  ║
      ║  None input. When PaymentService.validate() receives a    ║
      ║  request with missing 'amount' field, it passes None to   ║
      ║  check_amount(), which attempts float(None) → TypeError.  ║
      ║                                                           ║
      ║  Call Chain:                                              ║
      ║  handler.py:108 → payment.py:52 → validators.py:31        ║
      ║                                                           ║
      ║  Affected Files:                                          ║
      ║  - lib/validators.py (root cause)                         ║
      ║  - services/payment.py (missing input guard)              ║
      ║                                                           ║
      ║  Confidence: HIGH                                         ║
      ║  Impact: Payment flow completely blocked for null-amount  ║
      ║  requests. Affects ~15% of API traffic.                   ║
      ╚═══════════════════════════════════════════════════════════╝""")
    print(diag_output)
    info("  Token usage: 38,420 input + 1,280 output = 39,700 tokens")

    # ── Phase 2: Coding ──
    rule("PHASE 2 — Coding Agent (Fix Generation)", Colors.GREEN)
    step(4, "Loading source files into context...")

    agent_say("Coding", "Reading lib/validators.py and services/payment.py...")
    time.sleep(0.15)
    info("  ✓ Loaded 2 source files (892 lines total) into context window")
    info("  ✓ Analysed existing test patterns in tests/")

    step(5, "Generating fix patch & unit tests...")
    agent_say("Coding", "Generating minimal surgical fix...")
    time.sleep(0.3)

    fix_output = textwrap.dedent("""\
      ╔══ CODING REPORT ═══════════════════════════════════════════╗
      ║                                                            ║
      ║  Fix Patch (unified diff):                                 ║
      ║  ─────────────────────────────────────────────────────     ║
      ║  --- a/lib/validators.py                                   ║
      ║  +++ b/lib/validators.py                                   ║
      ║  @@ -28,6 +28,9 @@                                         ║
      ║   def check_amount(value):                                 ║
      ║  +    if value is None:                                    ║
      ║  +        raise ValueError("amount must not be None")      ║
      ║       return float(value)                                  ║
      ║  ─────────────────────────────────────────────────────     ║
      ║                                                            ║
      ║  New Unit Tests:                                           ║
      ║  ─────────────────────────────────────────────────────     ║
      ║  def test_check_amount_with_none_input():                  ║
      ║      with pytest.raises(ValueError, match="None"):          ║
      ║          check_amount(None)                                ║
      ║                                                            ║
      ║  def test_check_amount_with_valid_input():                 ║
      ║      assert check_amount("100.50") == 100.50               ║
      ║  ─────────────────────────────────────────────────────     ║
      ║                                                            ║
      ║  Modified files:  lib/validators.py                        ║
      ║  New test files:  tests/test_validators_fix.py             ║
      ╚════════════════════════════════════════════════════════════╝""")
    print(f"{Colors.GREEN}{fix_output}{Colors.RESET}")
    info("  Token usage: 12,600 input + 1,840 output = 14,440 tokens")

    # ── Phase 3: Review ──
    rule("PHASE 3 — Review Agent (Security & Quality Gate)", Colors.MAGENTA)
    step(6, "Running architectural review...")

    agent_say("Review", "Auditing fix against 5 criteria...")
    time.sleep(0.2)

    review_output = textwrap.dedent("""\
      ╔══ REVIEW REPORT ═══════════════════════════════════════════╗
      ║                                                            ║
      ║  Verdict:  APPROVE                                         ║
      ║                                                            ║
      ║  [✓] Security:     No injection vectors, no secrets leaked ║
      ║  [✓] Correctness:   Fix addresses root cause, not symptom  ║
      ║  [✓] Code Smell:    Clean, idiomatic, follows conventions  ║
      ║  [✓] Test Adequacy: 2 tests covering null & valid paths    ║
      ║  [✓] Backward Compat: Existing API surface unchanged       ║
      ║                                                            ║
      ║  Review Comment:                                           ║
      ║  "The null guard is correctly placed at the point of data  ║
      ║   ingress (check_amount). The ValueError provides clear    ║
      ║   diagnostics. Tests cover both the new edge case and the  ║
      ║   existing happy path. Approved for merge."                ║
      ╚════════════════════════════════════════════════════════════╝""")
    print(f"{Colors.MAGENTA}{review_output}{Colors.RESET}")
    info("  Token usage: 8,200 input + 920 output = 9,120 tokens")

    # ── Phase 4: Merge ──
    rule("PHASE 4 — Auto Merge Request", Colors.YELLOW)
    step(7, "Applying fix and creating Merge Request...")

    git_ops = textwrap.dedent("""\
      ╔══ GIT OPERATIONS ══════════════════════════════════════════╗
      ║                                                            ║
      ║  ✓ Branch created:   auto-heal/fix-a3f2b881                ║
      ║  ✓ Patch applied:    lib/validators.py                     ║
      ║  ✓ Test file added:  tests/test_validators_fix.py          ║
      ║  ✓ Commit:           2a7b16e - fix(auto-heal): add null    ║
      ║                      guard in check_amount()               ║
      ║  ✓ Pushed to:       origin/auto-heal/fix-a3f2b881          ║
      ║  ✓ MR Created:      https://github.com/yzc2908/.../pr/12   ║
      ║                                                            ║
      ╚════════════════════════════════════════════════════════════╝""")
    print(f"{Colors.YELLOW}{git_ops}{Colors.RESET}")

    # ── Summary ──
    rule("PIPELINE SUMMARY", Colors.CYAN)
    summary = textwrap.dedent(f"""\
      ╔══════════════════════════════════════════════════════════════╗
      ║  Pipeline Result:  SUCCESS                                   ║
      ║  Total Duration:   12.4 seconds                              ║
      ║  Agents Executed:  3 (Diagnostic → Coding → Review)         ║
      ║  LLM Calls:        3                                        ║
      ║  Retry Rounds:     0                                         ║
      ║  Total Tokens:     63,260 (input) + 4,040 (output)          ║
      ║                    = 67,300 tokens consumed                  ║
      ║                                                              ║
      ║  Fix Applied:       lib/validators.py (+3 lines)             ║
      ║  New Tests:         2 unit tests                             ║
      ║  MTTR:              ~12 sec (vs. ~4 hours manual)            ║
      ║  MTTR Reduction:    99.9%                                    ║
      ╚══════════════════════════════════════════════════════════════╝""")
    print(summary)

    info(f"\n  {Colors.BOLD}GitHub: https://github.com/yzc2908/microservice-auto-heal{Colors.RESET}")
    info(f"  {Colors.DIM}Model: Claude Opus 4.7 via Anthropic API{Colors.RESET}")
    print()


if __name__ == "__main__":
    main()
