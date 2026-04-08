"""
Visual heuristic grader - checks page aesthetics without screenshots or LLM.
Fast, deterministic, runs in < 1 second.

Scoring dimensions:
  - Has meaningful title (not "Document" / blank)      0.10
  - Has styled elements (non-default colors/fonts)     0.20
  - Has structured layout (header/main/footer or divs) 0.15
  - No console errors                                   0.10
  - Has interactive elements (buttons / inputs)        0.15
  - Reasonable content density (not empty)             0.15
  - Responsive viewport meta tag                       0.05
  - Semantic HTML usage                                0.10

Max total: 1.00
"""
from __future__ import annotations
from playwright.sync_api import Page


def visual_heuristic_score(page: Page) -> float:
    """
    Compute visual quality score in [0, 1].
    All checks are DOM-based, no screenshots needed.
    """
    score = 0.0

    # ── 1. Meaningful title ───────────────────────────────────────────────
    try:
        title = page.title() or ""
        if title and title.lower() not in ("document", "untitled", ""):
            score += 0.10
    except Exception:
        pass

    # ── 2. Styled elements ────────────────────────────────────────────────
    try:
        has_style = page.evaluate("""() => {
            // Check for inline styles, style tags, or linked stylesheets
            const styleSheets = document.styleSheets.length;
            const styleTags = document.querySelectorAll('style').length;
            const inlineStyles = document.querySelectorAll('[style]').length;
            const linkedCSS = document.querySelectorAll('link[rel="stylesheet"]').length;
            return (styleSheets + styleTags + inlineStyles + linkedCSS) > 0;
        }""")
        if has_style:
            score += 0.10
        # Check if any non-default background color is set
        has_color = page.evaluate("""() => {
            const els = document.querySelectorAll('*');
            for (let el of els) {
                const bg = window.getComputedStyle(el).backgroundColor;
                if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent'
                        && bg !== 'rgb(255, 255, 255)') {
                    return true;
                }
            }
            return false;
        }""")
        if has_color:
            score += 0.10
    except Exception:
        pass

    # ── 3. Structured layout ──────────────────────────────────────────────
    try:
        has_structure = page.evaluate("""() => {
            const structural = ['header', 'main', 'footer', 'nav', 'section', 'article', 'aside'];
            for (const tag of structural) {
                if (document.querySelector(tag)) return true;
            }
            // Or has multiple meaningful divs with ids/classes
            const divsWithAttrs = document.querySelectorAll('div[id], div[class]');
            return divsWithAttrs.length >= 2;
        }""")
        if has_structure:
            score += 0.15
    except Exception:
        pass

    # ── 4. No console errors (check for error elements) ───────────────────
    try:
        no_visible_errors = page.evaluate("""() => {
            const body = document.body ? document.body.innerText.toLowerCase() : '';
            const hasErrorText = body.includes('traceback') ||
                                 body.includes('syntaxerror') ||
                                 body.includes('referenceerror') ||
                                 body.includes('internal server error') ||
                                 body.includes('500 error');
            return !hasErrorText;
        }""")
        if no_visible_errors:
            score += 0.10
    except Exception:
        score += 0.10  # Benefit of the doubt if we can't check

    # ── 5. Interactive elements ───────────────────────────────────────────
    try:
        has_interactive = page.evaluate("""() => {
            const buttons = document.querySelectorAll('button, input[type="submit"], input[type="button"]').length;
            const inputs = document.querySelectorAll('input:not([type="hidden"]), textarea, select').length;
            return (buttons + inputs) >= 2;
        }""")
        if has_interactive:
            score += 0.15
    except Exception:
        pass

    # ── 6. Content density ────────────────────────────────────────────────
    try:
        content_ok = page.evaluate("""() => {
            const body = document.body;
            if (!body) return false;
            const text = body.innerText.trim();
            // At least 50 chars of content, not just boilerplate
            return text.length >= 50;
        }""")
        if content_ok:
            score += 0.15
    except Exception:
        pass

    # ── 7. Viewport meta tag ──────────────────────────────────────────────
    try:
        has_viewport = page.evaluate("""() => {
            const meta = document.querySelector('meta[name="viewport"]');
            return meta !== null;
        }""")
        if has_viewport:
            score += 0.05
    except Exception:
        pass

    # ── 8. Semantic HTML ──────────────────────────────────────────────────
    try:
        has_semantic = page.evaluate("""() => {
            const semanticTags = ['h1', 'h2', 'h3', 'ul', 'ol', 'li', 'table', 'form', 'label'];
            let found = 0;
            for (const tag of semanticTags) {
                if (document.querySelector(tag)) found++;
            }
            return found >= 2;
        }""")
        if has_semantic:
            score += 0.10
    except Exception:
        pass

    return round(min(1.0, max(0.0, score)), 3)


def get_visual_details(page: Page) -> str:
    """
    Return a human-readable summary of visual checks for the feedback string.
    """
    details = []

    try:
        title = page.title() or ""
        if title and title.lower() not in ("document", "untitled", ""):
            details.append(f"title='{title[:30]}'")
        else:
            details.append("no meaningful title")
    except Exception:
        pass

    try:
        num_sheets = page.evaluate("() => document.styleSheets.length")
        details.append(f"stylesheets={num_sheets}")
    except Exception:
        pass

    try:
        num_buttons = page.evaluate(
            "() => document.querySelectorAll('button, input[type=submit]').length"
        )
        num_inputs = page.evaluate(
            "() => document.querySelectorAll('input:not([type=hidden]), textarea').length"
        )
        details.append(f"buttons={num_buttons} inputs={num_inputs}")
    except Exception:
        pass

    try:
        has_semantic = page.evaluate("""() => {
            return ['h1','h2','ul','form','table'].filter(t => document.querySelector(t)).join(',')
        }""")
        if has_semantic:
            details.append(f"semantic=[{has_semantic}]")
    except Exception:
        pass

    try:
        text_len = page.evaluate("() => (document.body && document.body.innerText.length) || 0")
        details.append(f"text_chars={text_len}")
    except Exception:
        pass

    return " | ".join(details) if details else "No visual details available"
