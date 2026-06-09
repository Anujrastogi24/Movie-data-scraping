"""Shared Selenium plumbing for the scraping services.

Centralizes the bits every scraper needs so they don't each reinvent them:

* a headless-Chrome factory that reuses the project's bundled ``chromedriver.exe``
* explicit-wait helpers (``WebDriverWait`` + ``expected_conditions``) — no fixed
  ``time.sleep`` in the hot path
* a stale-element-safe retry wrapper
* a best-effort Cloudflare / "still loading" guard
* a generic ``retry`` decorator for flaky network/parse steps

Everything degrades gracefully: if Selenium or the driver binary is missing,
``selenium_available()`` returns False and callers fall back to ``requests``.
"""

from __future__ import annotations

import functools
import logging
import os
import time
from contextlib import contextmanager
from typing import Callable, Iterator, List, Optional, TypeVar

logger = logging.getLogger(__name__)

try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        StaleElementReferenceException,
        TimeoutException,
        WebDriverException,
    )
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    HAS_SELENIUM = True
except Exception:  # pragma: no cover - selenium optional
    HAS_SELENIUM = False
    WebDriver = object  # type: ignore
    WebElement = object  # type: ignore
    StaleElementReferenceException = TimeoutException = WebDriverException = Exception  # type: ignore

# Project root holds chromedriver.exe (see home/scraping.py for the original use).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHROMEDRIVER_PATH = os.path.join(PROJECT_ROOT, "chromedriver.exe")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_WAIT = 15        # seconds for explicit waits
PAGE_LOAD_TIMEOUT = 30   # seconds

T = TypeVar("T")


def selenium_available() -> bool:
    """True if Selenium is importable.

    We no longer require the bundled ``chromedriver.exe`` to exist: Selenium 4.6+
    ships *Selenium Manager*, which auto-resolves a driver matching the installed
    Chrome. ``get_driver`` tries the bundled binary first (offline-friendly) and
    falls back to Selenium Manager when it's missing or version-mismatched.
    """
    return HAS_SELENIUM


def retry(
    times: int = 3,
    exceptions: tuple = (Exception,),
    backoff: float = 0.5,
    label: str = "",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry a callable up to ``times`` with linear backoff.

    Backoff sleeps only fire *between* failed attempts, never on success, so the
    happy path has no artificial delay.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exc: Optional[Exception] = None
            for attempt in range(1, times + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # type: ignore[misc]
                    last_exc = exc
                    logger.warning(
                        "%s attempt %d/%d failed: %s",
                        label or func.__name__, attempt, times, exc,
                    )
                    if attempt < times:
                        time.sleep(backoff * attempt)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator


@contextmanager
def get_driver(headless: bool = True) -> Iterator["WebDriver"]:
    """Yield a configured Chrome driver, always quitting it afterwards.

    Raises RuntimeError if Selenium/driver are unavailable so callers can catch
    and fall back to a requests-based path.
    """
    if not selenium_available():
        raise RuntimeError("Selenium or chromedriver.exe is not available.")

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"user-agent={USER_AGENT}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = _start_chrome(options)
    try:
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        yield driver
    finally:
        try:
            driver.quit()
        except Exception:  # pragma: no cover - defensive
            pass


def _start_chrome(options: "Options") -> "WebDriver":
    """Start Chrome, preferring the bundled driver but falling back gracefully.

    1. Bundled ``chromedriver.exe`` — fast/offline, but breaks when its version
       lags the installed Chrome (the classic "only supports Chrome version N").
    2. Selenium Manager (explicit resolve) — ask Selenium Manager to *download* a
       driver matching the installed Chrome into its own cache and use that exact
       path. We resolve explicitly (rather than the bare ``webdriver.Chrome()``
       form) because a stale ``chromedriver.exe`` on PATH — e.g. the bundled v114
       in the project root — gets picked up first and re-triggers the very
       "only supports Chrome version N" mismatch we're trying to escape.

    Needs one-time internet access for the download; afterwards it's cached.
    """
    errors = []
    if os.path.exists(CHROMEDRIVER_PATH):
        try:
            return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)
        except WebDriverException as exc:
            errors.append(f"bundled chromedriver: {exc.msg or exc}")
            logger.info("Bundled chromedriver unusable (%s); resolving a matching driver "
                        "via Selenium Manager.", (exc.msg or str(exc)).splitlines()[0])

    try:
        driver_path = _resolve_chromedriver()
        return webdriver.Chrome(service=Service(driver_path), options=options)
    except WebDriverException as exc:
        errors.append(f"selenium manager: {exc}")
        raise RuntimeError("Could not start Chrome: " + " | ".join(errors)) from exc
    except Exception as exc:  # selenium-manager resolution failed (network/binary)
        errors.append(f"selenium manager: {exc}")
        raise RuntimeError("Could not start Chrome: " + " | ".join(errors)) from exc


def _resolve_chromedriver() -> str:
    """Return an absolute path to a chromedriver matching the installed Chrome.

    Drives Selenium Manager directly so it downloads/caches the right driver for
    the local Chrome version, ignoring any mismatched ``chromedriver`` on PATH.
    """
    from selenium.webdriver.common.selenium_manager import SeleniumManager

    paths = SeleniumManager().binary_paths(["--browser", "chrome"])
    driver_path = paths.get("driver_path")
    if not driver_path or not os.path.exists(driver_path):
        raise RuntimeError(f"Selenium Manager returned no usable driver_path ({paths!r}).")
    logger.info("Selenium Manager resolved chromedriver: %s", driver_path)
    return driver_path


def wait_for(driver: "WebDriver", by: str, selector: str, timeout: int = DEFAULT_WAIT) -> Optional["WebElement"]:
    """Explicitly wait for a single element to be present. Returns None on timeout."""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
    except TimeoutException:
        logger.debug("wait_for timed out for %s=%r", by, selector)
        return None


def wait_for_all(driver: "WebDriver", by: str, selector: str, timeout: int = DEFAULT_WAIT) -> List["WebElement"]:
    """Explicitly wait for >=1 elements; return them (or [] on timeout)."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_all_elements_located((by, selector))
        )
        return driver.find_elements(by, selector)
    except TimeoutException:
        logger.debug("wait_for_all timed out for %s=%r", by, selector)
        return []


def safe_text(element: "WebElement", default: str = "") -> str:
    """Read ``element.text`` guarding against stale references."""
    for _ in range(3):
        try:
            return (element.text or "").strip()
        except StaleElementReferenceException:
            time.sleep(0.2)
        except Exception:
            break
    return default


def safe_attr(element: "WebElement", name: str, default: str = "") -> str:
    """Read an attribute guarding against stale references."""
    for _ in range(3):
        try:
            return (element.get_attribute(name) or "").strip()
        except StaleElementReferenceException:
            time.sleep(0.2)
        except Exception:
            break
    return default


def handle_loading_screen(driver: "WebDriver", timeout: int = DEFAULT_WAIT) -> bool:
    """Best-effort wait past Cloudflare / JS loading interstitials.

    Waits for ``document.readyState == 'complete'`` and for a non-trivial
    <body>. Returns True if the page looks loaded, False if it still looks like
    a challenge page. We never try to *defeat* a challenge — only to wait it out.
    """
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        return False

    try:
        title = (driver.title or "").lower()
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        return True

    challenge_markers = ("just a moment", "checking your browser",
                         "verify you are human", "cloudflare")
    if any(marker in title or marker in body for marker in challenge_markers):
        # Give the challenge a chance to auto-resolve, then re-check once.
        try:
            WebDriverWait(driver, timeout).until_not(
                lambda d: any(m in (d.title or "").lower() for m in challenge_markers)
            )
            return True
        except TimeoutException:
            logger.info("Loading/challenge screen did not clear in time.")
            return False
    return True
