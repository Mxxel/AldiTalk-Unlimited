"""Automate ALDI TALK login and monitor the account overview.

Credentials and browser settings are loaded from a YAML configuration file.
The script opens the ALDI TALK website, accepts consent dialogs, signs in,
and periodically refreshes the account page. If the expected account markers
disappear, it saves a full-page screenshot for diagnosis and keeps refreshing.
The browser stays open until you close it.
"""

from __future__ import annotations

import argparse
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

# Account page reached after the OAuth redirect. It often reloads once before
# the refresh loop should take over.
ACCOUNT_OVERVIEW_PATH = "/portal/auth/uebersicht"


# Load and validate credentials and browser settings from YAML. Returns the
# normalized settings mapping and raises ValueError when required values fail validation.
def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as config_file:
        config: Any = yaml.safe_load(config_file)

    if not isinstance(config, dict):
        raise ValueError(f"{path} must contain a YAML mapping")

    missing = [
        key
        for key in (
            "phonenumber",
            "password",
            "headless",
            "delay-minimum",
            "delay-maximum",
        )
        if key not in config
    ]
    if missing:
        raise ValueError(f"Missing required config value(s): {', '.join(missing)}")

    if not config["phonenumber"] or not config["password"]:
        raise ValueError("phonenumber and password must not be empty")
    if not isinstance(config["headless"], bool):
        raise ValueError("headless must be either true or false")
    for key in ("delay-minimum", "delay-maximum"):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"{key} must be a positive number of seconds")
    if config["delay-minimum"] > config["delay-maximum"]:
        raise ValueError("delay-minimum must not be greater than delay-maximum")

    return {
        "phonenumber": str(config["phonenumber"]),
        "password": str(config["password"]),
        "headless": config["headless"],
        "delay-minimum": config["delay-minimum"],
        "delay-maximum": config["delay-maximum"],
    }


# Locate the Usercentrics accept button whose visible label contains `text`.
def consent_button(page: Any, text: str) -> Any:
    return page.get_by_test_id("uc-accept-all-button").filter(has_text=text)


# Wait for the consent button matching `text` to become visible, then click it.
def accept_cookies(page: Any, text: str = "Alle akzeptieren") -> None:
    button = consent_button(page, text)
    button.wait_for(state="visible")
    button.click()


# Return the current page URL, or an empty string while a navigation replaces it.
def page_url(page: Any) -> str:
    try:
        url = page.url
    except Exception:
        return ""
    return url if isinstance(url, str) else ""


# Report whether the consent button is currently visible without waiting.
def consent_button_is_visible(button: Any) -> bool:
    try:
        return button.is_visible() is True
    except Exception:
        return False


# Give the overview's follow-up reload time to finish before the refresh loop.
def wait_for_overview_to_settle(page: Any) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        return
    try:
        page.wait_for_timeout(1000)
    except Exception:
        return
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        return


# Click the post-login consent button when it appears. After login the browser
# can land on the account overview and reload that same URL without showing the
# dialog; return in that case so the refresh loop can start instead of timing out.
def accept_post_login_consent(
    page: Any, text: str = "Akzeptieren", timeout_ms: int = 30000
) -> None:
    button = consent_button(page, text)
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        if consent_button_is_visible(button):
            button.click()
            return
        if ACCOUNT_OVERVIEW_PATH in page_url(page):
            wait_for_overview_to_settle(page)
            if consent_button_is_visible(button):
                button.click()
            return
        if time.monotonic() >= deadline:
            break
        page.wait_for_timeout(250)
    raise TimeoutError(
        "Timed out waiting for the post-login consent dialog or the account overview"
    )


# Fill and submit the login form using the supplied account credentials.
def complete_login(page: Any, phonenumber: str, password: str) -> None:
    phone_input = page.locator('input.input__control[placeholder="Rufnummer"]')
    phone_input.wait_for(state="visible")
    phone_input.fill(phonenumber)
    page.wait_for_timeout(5000)

    password_input = page.locator(
        'input.input__control[placeholder="Passwort eingeben"]:visible'
    )
    password_input.wait_for(state="visible")
    password_input.fill(password)

    login_button = page.locator(
        "a.button.button--solid.button--medium.button--color-default."
        "button--has-label[href=\"#\"]:visible"
    )
    login_button.wait_for(state="visible")
    login_button.click()
    page.wait_for_load_state("domcontentloaded")


# Open the login flow from the ALDI TALK site, accept consent, and authenticate.
def continue_to_login(page: Any, phonenumber: str, password: str) -> None:
    nav_link = page.locator("span.nav-service__text:visible").filter(
        has_text="Mein ALDI TALK"
    )
    nav_link.wait_for(state="visible")
    nav_link.click()
    page.wait_for_url("https://login.alditalk-kundenbetreuung.de/**")

    # The live page spells this "Akzeptieren". The alternate spelling keeps the
    # locator compatible with the requested "Aktzeptieren" label as well.
    accept_cookies(page, "Akzeptieren")
    complete_login(page, phonenumber, password)
    accept_post_login_consent(page, "Akzeptieren")
    page.wait_for_timeout(5000)


# Seconds to wait after a failed attempt so a broken page cannot spin the loop.
RECOVERY_PAUSE_SECONDS = 5


# Playwright's Error.message when present, otherwise the normal exception text.
def error_text(exc: BaseException) -> str:
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message:
        return message
    return str(exc)


# A renderer crash. The browser process is still running.
def is_crash_error(exc: BaseException) -> bool:
    return "crash" in error_text(exc).lower()


# The page, context, or browser target is gone. Tab close and window close share
# this wording; browser_disconnected() tells those cases apart.
def is_closed_error(exc: BaseException) -> bool:
    text = error_text(exc).lower()
    return "has been closed" in text or "target closed" in text


# One line, without Playwright's call log. A failed fill() records the value
# there, and that value can be the account password.
def safe_error(exc: BaseException) -> str:
    text = error_text(exc).split("\nCall log:", 1)[0].strip()
    first_line = text.splitlines()[0] if text else ""
    if first_line:
        return f"{type(exc).__name__}: {first_line}"
    return type(exc).__name__


# True only when Chromium is gone. A "connection closed" message is not enough:
# the same words can show up while the window is still open, and returning from
# run() would make Playwright stop that window.
def browser_disconnected(
    browser: Any | None, _exc: BaseException | None = None
) -> bool:
    if browser is None:
        return False
    try:
        return browser.is_connected() is False
    except Exception:
        return True


# True when this tab has been closed. A crashed tab stays open.
def page_was_closed(page: Any) -> bool:
    try:
        return page.is_closed() is True
    except Exception as exc:
        return is_closed_error(exc)


# The current tab cannot be used anymore, while the browser may still be open.
def page_needs_replacement(page: Any, exc: BaseException | None = None) -> bool:
    if page_was_closed(page):
        return True
    if exc is None:
        return False
    return is_crash_error(exc) or is_closed_error(exc)


# Wait before the next attempt. Return False when this tab is no longer usable.
# A failed wait still sleeps so a crashed tab cannot spin the retry loop.
def pause_page(page: Any, seconds: float) -> bool:
    try:
        page.wait_for_timeout(int(seconds * 1000))
    except Exception as exc:
        time.sleep(seconds)
        if page_needs_replacement(page, exc):
            return False
    return not page_was_closed(page)


# Open another tab in the same browser, then drop the dead tab. Never closes
# the browser process; the caller keeps the window until the user closes it.
def open_replacement_page(context: Any, page: Any) -> Any:
    try:
        replacement = context.new_page()
    except Exception as exc:
        print(
            "Could not open a new tab; keeping the browser open: "
            f"{safe_error(exc)}"
        )
        return page
    try:
        if page.is_closed() is not True:
            page.close()
    except Exception:
        pass
    return replacement


# Replace a crashed or closed tab and say which of the two happened.
def replace_unusable_page(
    context: Any,
    page: Any,
    exc: BaseException | None = None,
    *,
    crashed: bool = False,
) -> Any:
    crashed = crashed or (
        exc is not None and is_crash_error(exc) and not page_was_closed(page)
    )
    if crashed:
        print("The page crashed; opening a new tab in the same browser.")
    else:
        print("The page stopped; opening a new tab in the same browser.")
    return open_replacement_page(context, page)


# Click the usage action when a meter below 50 has a value less than 3.5.
# A bad reading or a missing button is skipped so the refresh loop keeps running.
def check_usage_meter(page: Any) -> None:
    meters = page.locator("svg.usage-meter__graph")
    for index in range(meters.count()):
        meter = meters.nth(index)
        aria_value = meter.get_attribute("aria-valuenow")
        if aria_value is None:
            continue

        try:
            value = float(aria_value)
        except ValueError:
            continue
        if value >= 50:
            continue
        if value >= 3.5:
            return

        button = page.locator(
            "button.button--solid.button--medium.button--color-default."
            "button--has-label.button--circle:visible"
        ).first
        try:
            button.wait_for(state="visible")
            button.click()
        except Exception as exc:
            if page_needs_replacement(page, exc):
                raise
            print(
                "Usage action button was not clickable; keeping the browser open."
            )
        return


# Refresh the account page until the browser or this tab is no longer usable.
# Missing account markers are recorded and the loop continues. Session-expiry
# login failures stay in the loop as well. A renderer crash returns so the
# caller can open a new tab in the same browser.
def monitor_page(
    page: Any,
    phonenumber: str,
    password: str,
    random_delay: Callable[[float, float], float] = random.uniform,
    delay_minimum: float = 30,
    delay_maximum: float = 90,
    screenshot_dir: Path | None = None,
    browser: Any | None = None,
) -> None:
    screenshot_dir = screenshot_dir or Path(__file__).resolve().parent
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    while not browser_disconnected(browser):
        if page_was_closed(page):
            return
        try:
            delay_seconds = random_delay(delay_minimum, delay_maximum)
            page.wait_for_timeout(int(delay_seconds * 1000))
            page.reload(wait_until="domcontentloaded")

            session_expired = page.get_by_text(
                "Sitzung abgelaufen. Bitte melde dich erneut an.", exact=False
            ).count() > 0
            if session_expired:
                try:
                    complete_login(page, phonenumber, password)
                    page.wait_for_timeout(5000)
                except Exception as exc:
                    if browser_disconnected(browser, exc) or page_needs_replacement(
                        page, exc
                    ):
                        raise
                    print(
                        "Login after session expiry failed; "
                        f"keeping the browser open: {safe_error(exc)}"
                    )
                continue

            try:
                check_usage_meter(page)
            except Exception as exc:
                if browser_disconnected(browser, exc) or page_needs_replacement(
                    page, exc
                ):
                    raise
                print(
                    "Usage meter check failed; keeping the browser open: "
                    f"{safe_error(exc)}"
                )

            has_payment_marker = page.get_by_text(
                "Zahlung per Bankkonto", exact=False
            ).count() > 0
            has_balance_marker = (
                page.get_by_text("Dein Guthaben:", exact=False).count() > 0
            )
            if has_payment_marker and has_balance_marker:
                continue

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            screenshot_path = screenshot_dir / f"alditalk-unexpected-{timestamp}.png"
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception as exc:
                if browser_disconnected(browser, exc) or page_needs_replacement(
                    page, exc
                ):
                    raise
                print(
                    "Could not save a screenshot; "
                    f"keeping the browser open: {safe_error(exc)}"
                )
                continue
            for old_screenshot in screenshot_dir.glob("alditalk-unexpected-*.png"):
                if old_screenshot != screenshot_path:
                    old_screenshot.unlink(missing_ok=True)
            print(f"Unexpected page detected; screenshot saved to {screenshot_path}")
        except Exception as exc:
            if browser_disconnected(browser, exc):
                return
            if page_needs_replacement(page, exc):
                return
            print(f"Refresh failed; keeping the browser open: {safe_error(exc)}")
            if not pause_page(page, RECOVERY_PAUSE_SECONDS):
                return


# Headers a German desktop Chrome sends on every request. Accept and the
# Sec-Fetch-* headers stay with Chromium so they still vary per request.
BROWSER_ACCEPT_LANGUAGE = "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"
_DESKTOP_CONTEXT_KEYS = (
    "viewport",
    "screen",
    "device_scale_factor",
    "is_mobile",
    "has_touch",
)


# Launch Chromium without Playwright's automation switch. Pages read that
# switch as navigator.webdriver.
def browser_launch_options(headless: bool) -> dict[str, Any]:
    return {
        "headless": headless,
        "ignore_default_args": ["--enable-automation"],
        "args": ["--disable-blink-features=AutomationControlled"],
    }


# Build a desktop Chrome context for a German ALDI TALK session. The preset
# user agent is omitted so Chromium sends its own User-Agent and matching
# Sec-CH-UA client hints.
def browser_context_options(device: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {
        key: device[key] for key in _DESKTOP_CONTEXT_KEYS if key in device
    }
    options["locale"] = "de-DE"
    options["timezone_id"] = "Europe/Berlin"
    options["extra_http_headers"] = {"Accept-Language": BROWSER_ACCEPT_LANGUAGE}
    return options


# Open the public site, accept consent, and sign in. Failures propagate so the
# caller can retry them without closing the browser.
def sign_in(page: Any, phonenumber: str, password: str) -> None:
    page.goto("https://www.alditalk.de", wait_until="domcontentloaded")
    accept_cookies(page)
    continue_to_login(page, phonenumber, password)


# Keep Chromium open until its process disconnects. Errors, missing pages, and
# crashed tabs are retried in this same browser. Leaving this function while the
# browser is still connected would make Playwright stop the process.
def hold_browser_open(
    browser: Any,
    context: Any,
    page: Any,
    phonenumber: str,
    password: str,
    delay_minimum: float,
    delay_maximum: float,
) -> None:
    while not browser_disconnected(browser):
        if page_was_closed(page):
            page = replace_unusable_page(context, page)
            if browser_disconnected(browser):
                break
            if page_was_closed(page):
                pause_page(page, RECOVERY_PAUSE_SECONDS)
                continue
        try:
            sign_in(page, phonenumber, password)
        except Exception as exc:
            if browser_disconnected(browser, exc):
                break
            print(f"Sign-in failed; keeping the browser open: {safe_error(exc)}")
            if page_needs_replacement(page, exc):
                page = replace_unusable_page(context, page, exc)
            if browser_disconnected(browser):
                break
            pause_page(page, RECOVERY_PAUSE_SECONDS)
            continue

        if browser_disconnected(browser) or page_was_closed(page):
            continue
        try:
            monitor_page(
                page,
                phonenumber,
                password,
                delay_minimum=delay_minimum,
                delay_maximum=delay_maximum,
                browser=browser,
            )
        except Exception as exc:
            if browser_disconnected(browser, exc):
                break
            print(f"Refresh failed; keeping the browser open: {safe_error(exc)}")
            if page_needs_replacement(page, exc):
                page = replace_unusable_page(context, page, exc)
            if browser_disconnected(browser):
                break
            pause_page(page, RECOVERY_PAUSE_SECONDS)
            continue

        if browser_disconnected(browser):
            break
        if page_was_closed(page):
            pause_page(page, RECOVERY_PAUSE_SECONDS)
            continue
        page = replace_unusable_page(context, page, crashed=True)
        pause_page(page, RECOVERY_PAUSE_SECONDS)


# Load configuration and run until the user closes the browser window.
def run(config_path: Path) -> None:
    credentials = load_config(config_path)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            **browser_launch_options(credentials["headless"])
        )
        context = None
        page = None
        # Playwright closes Chromium when this function returns. Stay here
        # until the browser process is actually gone, and restart the session
        # if it stops early while the window is still open.
        while not browser_disconnected(browser):
            try:
                if context is None:
                    context = browser.new_context(
                        **browser_context_options(
                            playwright.devices["Desktop Chrome"]
                        )
                    )
                if page is None or page_was_closed(page):
                    page = context.new_page()
                hold_browser_open(
                    browser,
                    context,
                    page,
                    credentials["phonenumber"],
                    credentials["password"],
                    credentials["delay-minimum"],
                    credentials["delay-maximum"],
                )
            except Exception as exc:
                if browser_disconnected(browser):
                    break
                print(
                    "Keeping the browser open after an error: "
                    f"{safe_error(exc)}"
                )
            if browser_disconnected(browser):
                break
            time.sleep(RECOVERY_PAUSE_SECONDS)
        print("Browser closed.")


# Parse command-line arguments and start the ALDI TALK workflow.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to the YAML credentials file (default: config.yaml)",
    )
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
