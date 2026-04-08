"""
Usability helpers for safe browser interactions.
All functions are deterministic and return (success, message) tuples.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple
from playwright.sync_api import Page


@dataclass
class ElementCheck:
    """Result of checking a single UI element."""
    selector: str
    exists: bool = False
    visible: bool = False
    enabled: bool = False
    text: str = ""
    value: str = ""
    tag: str = ""
    classes: list = field(default_factory=list)
    attributes: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def usable(self) -> bool:
        """Element is present, visible, and enabled."""
        return self.exists and self.visible and self.enabled


def check_element_usability(page: Page, selector: str, timeout: int = 2000) -> ElementCheck:
    """
    Check whether a DOM element is usable (exists, visible, enabled).
    Returns an ElementCheck dataclass. Never raises.
    """
    check = ElementCheck(selector=selector)
    try:
        el = page.query_selector(selector)
        if el is None:
            check.error = f"Element '{selector}' not found in DOM"
            return check

        check.exists = True
        check.visible = el.is_visible()
        check.enabled = el.is_enabled()
        check.tag = (el.evaluate("e => e.tagName") or "").lower()

        # Text content
        try:
            check.text = (el.inner_text() or "").strip()
        except Exception:
            pass

        # Input value
        try:
            if check.tag in ("input", "textarea", "select"):
                check.value = el.input_value() or ""
        except Exception:
            pass

        # CSS classes
        try:
            cls = el.get_attribute("class") or ""
            check.classes = cls.split() if cls else []
        except Exception:
            pass

        # Key attributes
        for attr in ("id", "name", "type", "href", "placeholder", "disabled", "aria-label"):
            try:
                val = el.get_attribute(attr)
                if val is not None:
                    check.attributes[attr] = val
            except Exception:
                pass

    except Exception as e:
        check.error = str(e)

    return check


def safe_click(page: Page, selector: str, timeout: int = 5000) -> Tuple[bool, str]:
    """
    Click an element safely. Returns (success, message).
    Waits for element to be visible and enabled before clicking.
    """
    if not selector:
        return False, "Error: selector is required for browser_click"

    try:
        # Wait for element
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        el = page.query_selector(selector)
        if el is None:
            return False, f"Element '{selector}' not found after wait"

        if not el.is_enabled():
            return False, f"Element '{selector}' is disabled"

        el.click(timeout=timeout)
        return True, f"Clicked '{selector}'"

    except Exception as e:
        err = str(e)
        # Provide helpful messages for common failures
        if "timeout" in err.lower():
            return False, f"Timeout waiting for '{selector}' to be visible"
        if "not visible" in err.lower():
            return False, f"Element '{selector}' exists but is not visible"
        return False, f"Click failed on '{selector}': {err[:200]}"


def safe_fill(page: Page, selector: str, value: str, timeout: int = 5000) -> Tuple[bool, str]:
    """
    Fill an input element safely. Returns (success, message).
    Clears existing content before filling.
    """
    if not selector:
        return False, "Error: selector is required for browser_fill"

    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        el = page.query_selector(selector)
        if el is None:
            return False, f"Input '{selector}' not found after wait"

        tag = (el.evaluate("e => e.tagName") or "").lower()
        if tag not in ("input", "textarea", "select"):
            # Try filling anyway (some custom inputs)
            pass

        if not el.is_enabled():
            return False, f"Input '{selector}' is disabled"

        # Clear and fill
        el.click()
        el.fill(value)
        return True, f"Filled '{selector}' with '{value[:50]}{'...' if len(value) > 50 else ''}'"

    except Exception as e:
        err = str(e)
        if "timeout" in err.lower():
            return False, f"Timeout waiting for '{selector}'"
        return False, f"Fill failed on '{selector}': {err[:200]}"


def safe_get_text(page: Page, selector: str, timeout: int = 3000) -> Tuple[Optional[str], str]:
    """
    Get text content of an element. Returns (text_or_None, message).
    """
    if not selector:
        return None, "Error: selector is required for browser_get_text"

    try:
        page.wait_for_selector(selector, timeout=timeout)
        el = page.query_selector(selector)
        if el is None:
            return None, f"Element '{selector}' not found"

        text = el.inner_text() or ""
        return text.strip(), f"Got text from '{selector}'"

    except Exception as e:
        err = str(e)
        if "timeout" in err.lower():
            return None, f"Timeout: '{selector}' not found within {timeout}ms"
        return None, f"Error getting text from '{selector}': {err[:200]}"


def check_text_visible(page: Page, text: str, case_sensitive: bool = False) -> Tuple[bool, str]:
    """
    Check if given text is visible anywhere on the page.
    Returns (found, message).
    """
    try:
        body_text = page.inner_text("body") or ""
        if not case_sensitive:
            found = text.lower() in body_text.lower()
        else:
            found = text in body_text
        if found:
            return True, f"Text '{text[:50]}' found on page"
        else:
            return False, f"Text '{text[:50]}' NOT found on page"
    except Exception as e:
        return False, f"Error checking text visibility: {e}"
