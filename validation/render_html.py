"""Re-run the QuantLib cross-validation suite and render ``REPORT.md`` to HTML.

This script does two things every time it runs:

1. Invokes ``pytest validation/quantlib_xref -v --tb=line``, capturing pass/fail
   and the per-pair Black-Scholes pricing diagnostics emitted by
   ``test_bs_pricing_agrees_with_quantlib``. The output is appended to the
   generated HTML so the report records *what this run actually measured*,
   not just the prose written at some earlier commit.
2. Converts ``validation/REPORT.md`` to ``validation/REPORT.html`` using the
   ``markdown`` package (tables, fenced code, and inline-style HTML are
   supported via the bundled extensions). A small embedded stylesheet makes
   the HTML readable without external resources.

Invocation::

    .venv/Scripts/python validation/render_html.py

Requires the ``[validation]`` optional extra (``QuantLib`` + ``markdown``).
"""

from __future__ import annotations

import datetime as _dt
import html as _html
import subprocess
import sys
from pathlib import Path

import markdown as _md

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_MD_PATH = _HERE / "REPORT.md"
_HTML_PATH = _HERE / "REPORT.html"
_PY = sys.executable

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
:root {{
    --bg: #ffffff;
    --fg: #1a1a1a;
    --muted: #6a6a6a;
    --accent: #1f6feb;
    --border: #d6d6d6;
    --pass: #1a7f37;
    --fail: #b91c1c;
    --table-stripe: #f6f6f6;
    --code-bg: #f4f4f4;
}}
body {{
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    line-height: 1.55;
    margin: 0;
    padding: 2.5rem max(2rem, calc((100% - 50rem) / 2));
}}
h1, h2, h3 {{
    line-height: 1.25;
    margin-top: 2.2rem;
}}
h1 {{ font-size: 1.85rem; border-bottom: 1px solid var(--border); padding-bottom: 0.4rem; }}
h2 {{ font-size: 1.35rem; border-bottom: 1px solid var(--border); padding-bottom: 0.25rem; }}
h3 {{ font-size: 1.1rem; }}
a  {{ color: var(--accent); }}
table {{
    border-collapse: collapse;
    margin: 1rem 0;
    width: 100%;
    font-size: 0.92rem;
}}
th, td {{
    border: 1px solid var(--border);
    padding: 6px 10px;
    text-align: left;
    vertical-align: top;
}}
tbody tr:nth-child(odd) {{ background: var(--table-stripe); }}
code {{
    background: var(--code-bg);
    padding: 0.05rem 0.3rem;
    border-radius: 3px;
    font-size: 0.92em;
}}
pre {{
    background: var(--code-bg);
    padding: 0.75rem 1rem;
    border-radius: 5px;
    overflow-x: auto;
    font-size: 0.85rem;
    line-height: 1.4;
}}
pre code {{ background: transparent; padding: 0; }}
.run-banner {{
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.9rem 1.1rem;
    margin: 1.4rem 0 2rem 0;
    background: #fafbfc;
}}
.run-banner .status.pass {{ color: var(--pass); font-weight: 600; }}
.run-banner .status.fail {{ color: var(--fail); font-weight: 600; }}
.run-banner .meta {{ color: var(--muted); font-size: 0.88rem; margin-top: 0.3rem; }}
.run-output {{ margin-top: 0.7rem; }}
.run-output summary {{ cursor: pointer; color: var(--accent); }}
hr {{ border: none; border-top: 1px solid var(--border); margin: 2rem 0; }}
</style>
</head>
<body>
<div class="run-banner">
  <div>Last regenerated: <strong>{timestamp}</strong></div>
  <div>Cross-validation suite status:
       <span class="status {status_class}">{status_text}</span>
       ({passed} passed, {failed} failed)
  </div>
  <div class="meta">Run via <code>python validation/render_html.py</code>. See the embedded run log below.</div>
  <details class="run-output">
    <summary>Show pytest run log ({log_lines} lines)</summary>
    <pre>{run_log}</pre>
  </details>
</div>
{body}
</body>
</html>
"""


def run_validation_suite() -> tuple[str, int, int, int]:
    """Run the QL cross-validation suite, returning ``(log, passed, failed, exit_code)``.

    Returns
    -------
    tuple
        ``(combined_stdout_stderr, passed_count, failed_count, exit_code)``.
    """
    completed = subprocess.run(
        [
            _PY,
            "-m",
            "pytest",
            "validation/quantlib_xref",
            "-v",
            "--tb=line",
            "--no-header",
            "-rN",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    log = completed.stdout + ("\n" + completed.stderr if completed.stderr else "")
    passed = log.count(" PASSED")
    failed = log.count(" FAILED")
    return log, passed, failed, completed.returncode


def render(
    md_text: str,
    run_log: str,
    passed: int,
    failed: int,
    exit_code: int,
) -> str:
    """Render the Markdown body and the run banner into the HTML template.

    Parameters
    ----------
    md_text
        Raw Markdown content of ``REPORT.md``.
    run_log
        Captured pytest output to embed as a collapsible ``<details>``.
    passed
        Number of passing test cases in the run.
    failed
        Number of failing test cases in the run.
    exit_code
        pytest's exit code; ``0`` is reported as PASS, anything else as FAIL.

    Returns
    -------
    str
        A complete, self-contained HTML document.
    """
    body = _md.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
        output_format="html5",
    )
    status_ok = exit_code == 0 and failed == 0
    return _HTML_TEMPLATE.format(
        title="QuantLib Cross-Validation Report",
        timestamp=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status_class="pass" if status_ok else "fail",
        status_text="PASS" if status_ok else "FAIL",
        passed=passed,
        failed=failed,
        log_lines=run_log.count("\n"),
        run_log=_html.escape(run_log),
        body=body,
    )


def main() -> int:
    """Entry point: rerun the suite, regenerate ``REPORT.html``, return exit code.

    Returns
    -------
    int
        ``0`` if the suite passed and the HTML was written, ``1`` otherwise.
    """
    if not _MD_PATH.exists():
        print(f"ERROR: missing source file {_MD_PATH}", file=sys.stderr)
        return 1
    print(f"Running validation suite from {_REPO_ROOT} ...")
    log, passed, failed, exit_code = run_validation_suite()
    print(log)
    print(f"Summary: {passed} passed, {failed} failed, exit code {exit_code}")
    md_text = _MD_PATH.read_text(encoding="utf-8")
    html = render(md_text, log, passed, failed, exit_code)
    _HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {_HTML_PATH}")
    return 0 if exit_code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
