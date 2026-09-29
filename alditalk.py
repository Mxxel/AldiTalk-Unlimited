"""Automate ALDI TALK login and monitor the account overview.

Credentials and browser settings are loaded from a YAML configuration file.
The script opens the ALDI TALK website, accepts consent dialogs, signs in,
and periodically refreshes the account page. If the expected account markers
disappear, it saves a full-page screenshot for diagnosis.
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml


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


# Wait for the consent button matching `text` to become visible, then click it.
def accept_cookies(page: Any, text: str = "Alle akzeptieren") -> None:
    button = page.get_by_test_id("uc-accept-all-button").filter(has_text=text)
    button.wait_for(state="visible")
    button.click()


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
    accept_cookies(page, "Akzeptieren")
    page.wait_for_timeout(5000)


# Click the usage action when a meter below 50 has a value less than 3.5.
def check_usage_meter(page: Any) -> None:
    meters = page.locator("svg.usage-meter__graph")
    for index in range(meters.count()):
        meter = meters.nth(index)
        aria_value = meter.get_attribute("aria-valuenow")
        if aria_value is None:
            continue

        value = float(aria_value)
        if value >= 50:
            continue
        if value >= 3.5:
            return

        button = page.locator(
            "button.button--solid.button--medium.button--color-default."
            "button--has-label.button--circle:visible"
        ).first
        button.wait_for(state="visible")
        button.click()
        return


# Refresh the account page, re-login after session expiry, and save a full-page
# screenshot when expected account markers disappear; return the screenshot path.
def monitor_page(
    page: Any,
    phonenumber: str,
    password: str,
    random_delay: Callable[[float, float], float] = random.uniform,
    delay_minimum: float = 30,
    delay_maximum: float = 90,
    screenshot_dir: Path | None = None,
) -> Path:
    screenshot_dir = screenshot_dir or Path(__file__).resolve().parent
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    while True:
        delay_seconds = random_delay(delay_minimum, delay_maximum)
        page.wait_for_timeout(int(delay_seconds * 1000))
        page.reload(wait_until="domcontentloaded")

        session_expired = page.get_by_text(
            "Sitzung abgelaufen. Bitte melde dich erneut an.", exact=False
        ).count() > 0
        if session_expired:
            complete_login(page, phonenumber, password)
            page.wait_for_timeout(5000)
            continue

        check_usage_meter(page)

        has_payment_marker = page.get_by_text(
            "Zahlung per Bankkonto", exact=False
        ).count() > 0
        has_balance_marker = page.get_by_text("Dein Guthaben:", exact=False).count() > 0
        if has_payment_marker and has_balance_marker:
            continue

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        screenshot_path = screenshot_dir / f"alditalk-unexpected-{timestamp}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        return screenshot_path


# Load configuration, launch the browser workflow, and close the browser when done.
def run(config_path: Path) -> None:
    credentials = load_config(config_path)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=credentials["headless"])
        try:
            page = browser.new_page()
            page.goto("https://www.alditalk.de", wait_until="domcontentloaded")
            accept_cookies(page)
            continue_to_login(
                page, credentials["phonenumber"], credentials["password"]
            )
            screenshot_path = monitor_page(
                page,
                credentials["phonenumber"],
                credentials["password"],
                delay_minimum=credentials["delay-minimum"],
                delay_maximum=credentials["delay-maximum"],
            )
            print(f"Unexpected page detected; screenshot saved to {screenshot_path}")
        finally:
            browser.close()


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
