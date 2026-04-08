"""
Code quality grader. Checks syntax, complexity, structure, and security.
All checks are deterministic and run in < 2 seconds total.
No LLM calls.

Dimensions (each 0-1, then weighted):
  syntax      (0.30) - parseable, no obvious errors
  complexity  (0.25) - reasonable length, not deeply nested
  structure   (0.20) - good organization / naming
  security    (0.25) - no obvious security anti-patterns
"""
from __future__ import annotations
import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class QualityCheck:
    name: str
    score: float          # 0.0 – 1.0
    weight: float         # relative weight
    details: str          # short explanation
    passed: bool          # score >= 0.6


@dataclass
class CodeQualityResult:
    total_score: float
    syntax_score: float
    complexity_score: float
    structure_score: float
    security_score: float
    checks: List[QualityCheck]
    explanation: str


# ── Syntax Check ──────────────────────────────────────────────────────────

def score_syntax(workspace: str, framework: str) -> QualityCheck:
    """Parse source files and detect syntax errors. ~0.2s"""
    issues = []
    files_checked = 0

    ws = Path(workspace)

    if framework == "python":
        py_files = [f for f in ws.rglob("*.py")
                    if "__pycache__" not in str(f)]
        for f in py_files:
            files_checked += 1
            try:
                source = f.read_text(encoding="utf-8", errors="ignore")
                ast.parse(source, filename=str(f))
            except SyntaxError as e:
                issues.append(f"SyntaxError in {f.name}:{e.lineno}: {e.msg}")
            except Exception as e:
                issues.append(f"Parse error in {f.name}: {e}")

    elif framework == "nodejs":
        js_files = [f for f in ws.rglob("*.js")
                    if "node_modules" not in str(f)]
        for f in js_files:
            files_checked += 1
            try:
                result = subprocess.run(
                    ["node", "--check", str(f)],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode != 0:
                    first_line = (result.stderr or "").split("\n")[0]
                    issues.append(f"JS syntax error in {f.name}: {first_line[:100]}")
            except FileNotFoundError:
                # node not available, do basic checks
                source = f.read_text(encoding="utf-8", errors="ignore")
                # Check for obviously mismatched braces
                if source.count("{") != source.count("}"):
                    issues.append(f"Mismatched braces in {f.name}")
            except Exception as e:
                issues.append(f"Check error for {f.name}: {e}")

    else:  # html
        html_files = [f for f in ws.rglob("*.html")]
        for f in html_files:
            files_checked += 1
            try:
                source = f.read_text(encoding="utf-8", errors="ignore")
                # Basic HTML checks
                if not re.search(r'<!DOCTYPE\s+html', source, re.IGNORECASE):
                    issues.append(f"Missing DOCTYPE in {f.name}")
                # Check for unclosed script tags
                script_opens = len(re.findall(r'<script', source, re.IGNORECASE))
                script_closes = len(re.findall(r'</script>', source, re.IGNORECASE))
                if script_opens != script_closes:
                    issues.append(f"Mismatched <script> tags in {f.name}")
                # Check for unclosed style tags
                style_opens = len(re.findall(r'<style', source, re.IGNORECASE))
                style_closes = len(re.findall(r'</style>', source, re.IGNORECASE))
                if style_opens != style_closes:
                    issues.append(f"Mismatched <style> tags in {f.name}")
            except Exception as e:
                issues.append(f"Error reading {f.name}: {e}")

    if files_checked == 0:
        return QualityCheck("syntax", 0.3, 0.30, "No source files found", False)

    score = max(0.0, 1.0 - len(issues) * 0.25)
    detail = "; ".join(issues[:2]) if issues else f"No syntax errors in {files_checked} file(s)"
    return QualityCheck("syntax", round(score, 3), 0.30, detail, score >= 0.6)


# ── Complexity Check ──────────────────────────────────────────────────────

def score_complexity(workspace: str, framework: str) -> QualityCheck:
    """Check code complexity: length, nesting, function size. ~0.3s"""
    issues = []
    ws = Path(workspace)

    def get_main_sources() -> list:
        if framework == "python":
            return [f for f in ws.rglob("*.py") if "__pycache__" not in str(f)]
        elif framework == "nodejs":
            return [f for f in ws.rglob("*.js") if "node_modules" not in str(f)]
        else:
            return list(ws.rglob("*.html")) + list(ws.rglob("*.js"))

    sources = get_main_sources()
    if not sources:
        return QualityCheck("complexity", 0.5, 0.25, "No source files", True)

    for f in sources:
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            non_blank = [l for l in lines if l.strip()]

            # File too long (> 500 non-blank lines suggests unstructured dump)
            if len(non_blank) > 500:
                issues.append(f"{f.name} is very long ({len(non_blank)} lines)")

            # Check nesting depth (count indentation)
            max_indent = 0
            for line in lines:
                stripped = line.lstrip()
                if stripped:
                    indent = len(line) - len(stripped)
                    # Python: 4 spaces per level. JS: 2-4 spaces
                    level = indent // 2
                    max_indent = max(max_indent, level)

            if max_indent > 10:
                issues.append(f"{f.name} has deep nesting (indent level ~{max_indent})")

            # For Python: check function length
            if framework == "python" and f.suffix == ".py":
                try:
                    tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            func_lines = (node.end_lineno or 0) - node.lineno
                            if func_lines > 80:
                                issues.append(f"Long function '{node.name}' ({func_lines} lines) in {f.name}")
                except Exception:
                    pass

        except Exception:
            pass

    score = max(0.0, 1.0 - len(issues) * 0.20)
    detail = "; ".join(issues[:3]) if issues else "Complexity looks reasonable"
    return QualityCheck("complexity", round(score, 3), 0.25, detail, score >= 0.6)


# ── Structure Check ───────────────────────────────────────────────────────

def score_structure(workspace: str, framework: str) -> QualityCheck:
    """Check code organization, naming, and comments. ~0.2s"""
    issues = []
    positive = []
    ws = Path(workspace)

    if framework == "python":
        py_files = [f for f in ws.rglob("*.py") if "__pycache__" not in str(f)]

        for f in py_files:
            try:
                source = f.read_text(encoding="utf-8", errors="ignore")

                # Has docstrings or comments
                has_comments = bool(re.search(r'#.+|"""[\s\S]*?"""', source))
                if has_comments:
                    positive.append(f"comments in {f.name}")

                # Has proper function definitions
                func_count = len(re.findall(r'^def |^    def ', source, re.MULTILINE))
                if func_count >= 2:
                    positive.append(f"{func_count} functions in {f.name}")

                # Uses descriptive names (not single-letter variables widely)
                single_letter_vars = len(re.findall(r'\b[a-z]\s*=\s*(?!\s)', source))
                if single_letter_vars > 10:
                    issues.append(f"Many single-letter variables in {f.name}")

                # Has if __name__ == "__main__" guard
                if "if __name__" in source:
                    positive.append("main guard present")

                # Template directory for FastAPI
                templates_dir = ws / "templates"
                if templates_dir.exists() and templates_dir.is_dir():
                    html_count = len(list(templates_dir.glob("*.html")))
                    if html_count >= 2:
                        positive.append(f"{html_count} templates")
                    elif html_count == 0:
                        issues.append("templates/ exists but has no .html files")

            except Exception:
                pass

        # Check for requirements.txt
        if not (ws / "requirements.txt").exists():
            issues.append("No requirements.txt")

    elif framework == "nodejs":
        js_files = [f for f in ws.rglob("*.js") if "node_modules" not in str(f)]

        for f in js_files:
            try:
                source = f.read_text(encoding="utf-8", errors="ignore")

                # Has comments
                has_comments = bool(re.search(r'//|/\*', source))
                if has_comments:
                    positive.append(f"comments in {f.name}")

                # Uses const/let (modern JS)
                if re.search(r'\b(const|let)\b', source):
                    positive.append("uses const/let")
                elif re.search(r'\bvar\b', source):
                    issues.append("uses var instead of const/let")

                # Has route definitions
                route_count = len(re.findall(r'app\.(get|post|put|delete|patch)\s*\(', source))
                if route_count >= 2:
                    positive.append(f"{route_count} routes")
                elif route_count == 0:
                    issues.append("No Express routes found")

                # Uses require or import
                has_imports = bool(re.search(r'require\s*\(|import\s+', source))
                if has_imports:
                    positive.append("proper imports")

            except Exception:
                pass

        # Check for package.json
        if not (ws / "package.json").exists():
            issues.append("No package.json")

    else:  # html
        html_files = list(ws.rglob("*.html"))

        for f in html_files:
            try:
                source = f.read_text(encoding="utf-8", errors="ignore")

                # Has semantic tags
                semantic_tags = ["header", "main", "footer", "nav", "section", "article"]
                found_semantic = [t for t in semantic_tags if f"<{t}" in source.lower()]
                if found_semantic:
                    positive.append(f"semantic HTML: {', '.join(found_semantic[:3])}")

                # Has CSS (inline or linked)
                if re.search(r'<style|<link.*stylesheet', source, re.IGNORECASE):
                    positive.append("has CSS")

                # Has JavaScript
                if re.search(r'<script', source, re.IGNORECASE):
                    positive.append("has JavaScript")

                # Has comments
                if "<!--" in source or "//" in source:
                    positive.append("has comments")

                # IDs and classes used
                id_count = len(re.findall(r'\bid=["\']', source))
                class_count = len(re.findall(r'\bclass=["\']', source))
                if id_count + class_count >= 5:
                    positive.append(f"{id_count} IDs, {class_count} classes")
                elif id_count + class_count == 0:
                    issues.append("No id or class attributes")

            except Exception:
                pass

    # Score: start at 0.5, add for positives, subtract for issues
    score = 0.5 + min(0.5, len(positive) * 0.10) - min(0.5, len(issues) * 0.15)
    score = round(max(0.0, min(1.0, score)), 3)

    if positive and not issues:
        detail = "Good structure: " + ", ".join(positive[:3])
    elif issues:
        detail = "Issues: " + "; ".join(issues[:2])
    else:
        detail = "Adequate structure"

    return QualityCheck("structure", score, 0.20, detail, score >= 0.6)


# ── Security Check ────────────────────────────────────────────────────────

def score_security(workspace: str, framework: str) -> QualityCheck:
    """Pattern-based security check. No external tools. ~0.3s"""
    issues = []

    all_files = [f for f in Path(workspace).rglob("*")
                 if f.is_file()
                 and "node_modules" not in str(f)
                 and "__pycache__" not in str(f)
                 and f.suffix in (".py", ".js", ".html", ".css")]

    for f in all_files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")

            # SQLi: raw string formatting in queries
            if re.search(r'(?:execute|query)\s*\(\s*["\'].*?%s|f["\'].*?SELECT.*?\{', content, re.IGNORECASE):
                issues.append(f"Potential SQL injection in {f.name}")

            # XSS: innerHTML with user data
            if re.search(r'innerHTML\s*=\s*(?!`[^`]*`)[^;]*(?:req\.|request\.|input|param)', content):
                issues.append(f"Potential XSS via innerHTML in {f.name}")

            # eval() usage
            if re.search(r'\beval\s*\(', content):
                issues.append(f"eval() usage in {f.name}")

            # Hardcoded secrets (but allow demo/test values)
            if re.search(r'(?:password|secret|api_key)\s*=\s*["\'][^"\']{8,}["\']', content, re.IGNORECASE):
                # Allow obvious demo values
                if not re.search(r'(?:password|secret)\s*=\s*["\'](?:test|demo|example|placeholder|your_)', content, re.IGNORECASE):
                    issues.append(f"Possible hardcoded secret in {f.name}")

            # Path traversal risk
            if re.search(r'open\s*\(\s*(?:request|req|input|f["\'])', content):
                issues.append(f"Potential path traversal in {f.name}")

            # Debug mode in production
            if framework == "python" and re.search(r'debug\s*=\s*True', content, re.IGNORECASE):
                # Only flag if debug=True is at module level, not inside if __name__
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if re.search(r'debug\s*=\s*True', line, re.IGNORECASE):
                        # Check if it's inside an if __name__ block
                        in_main_guard = any(
                            "if __name__" in lines[j] for j in range(max(0, i-10), i)
                        )
                        if not in_main_guard:
                            issues.append(f"debug=True in {f.name}")
                            break

        except Exception:
            pass

    score = max(0.0, 1.0 - len(issues) * 0.20)
    detail = "; ".join(issues[:3]) if issues else "No obvious security issues"
    return QualityCheck("security", round(score, 3), 0.25, detail, score >= 0.6)


# ── Main Entry Point ──────────────────────────────────────────────────────

def compute_code_quality(workspace: str, framework: str) -> CodeQualityResult:
    """Run all checks and return combined result. Target < 2s."""
    syntax_check = score_syntax(workspace, framework)
    complexity_check = score_complexity(workspace, framework)
    structure_check = score_structure(workspace, framework)
    security_check = score_security(workspace, framework)

    checks = [syntax_check, complexity_check, structure_check, security_check]

    # Weighted average
    total = sum(c.score * c.weight for c in checks)
    total_weight = sum(c.weight for c in checks)
    total_score = round(total / total_weight if total_weight > 0 else 0.5, 3)

    # Build explanation
    parts = []
    for c in checks:
        icon = "✓" if c.passed else "✗"
        parts.append(f"{icon} {c.name}({c.score:.2f}): {c.details[:80]}")
    explanation = " | ".join(parts[:4])

    return CodeQualityResult(
        total_score=total_score,
        syntax_score=syntax_check.score,
        complexity_score=complexity_check.score,
        structure_score=structure_check.score,
        security_score=security_check.score,
        checks=checks,
        explanation=explanation
    )
