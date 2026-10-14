import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class AldiTalkScriptTests(unittest.TestCase):
    def test_load_config_reads_phone_number_and_password(self):
        from alditalk import load_config

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.yaml"
            config_path.write_text(
                "phonenumber: '+491701234567'\npassword: 'secret'\n"
                "headless: false\ndelay-minimum: 30\ndelay-maximum: 90\n",
                encoding="utf-8",
            )

            self.assertEqual(
                load_config(config_path),
                {
                    "phonenumber": "+491701234567",
                    "password": "secret",
                    "headless": False,
                    "delay-minimum": 30,
                    "delay-maximum": 90,
                },
            )

    def test_browser_launch_hides_the_automation_switch(self):
        from alditalk import browser_launch_options

        headed = browser_launch_options(False)
        headless = browser_launch_options(True)

        self.assertFalse(headed["headless"])
        self.assertTrue(headless["headless"])
        self.assertEqual(
            headed["ignore_default_args"], ["--enable-automation"]
        )
        self.assertEqual(
            headed["args"], ["--disable-blink-features=AutomationControlled"]
        )
        self.assertNotIn("Playwright", str(headed))
        self.assertNotIn("HeadlessChrome", str(headed))

    def test_browser_context_uses_german_desktop_headers(self):
        from alditalk import browser_context_options

        options = browser_context_options(
            {
                "user_agent": "Mozilla/5.0 HeadlessChrome Playwright",
                "viewport": {"width": 1280, "height": 720},
                "screen": {"width": 1280, "height": 720},
                "device_scale_factor": 1,
                "is_mobile": False,
                "has_touch": False,
                "default_browser_type": "chromium",
            }
        )

        self.assertNotIn("user_agent", options)
        self.assertNotIn("default_browser_type", options)
        self.assertEqual(options["locale"], "de-DE")
        self.assertEqual(options["timezone_id"], "Europe/Berlin")
        self.assertEqual(
            options["extra_http_headers"],
            {"Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7"},
        )
        self.assertEqual(options["viewport"], {"width": 1280, "height": 720})
        self.assertEqual(options["screen"], {"width": 1280, "height": 720})
        self.assertEqual(options["device_scale_factor"], 1)
        self.assertFalse(options["is_mobile"])
        self.assertFalse(options["has_touch"])
        rendered = str(options)
        self.assertNotIn("Playwright", rendered)
        self.assertNotIn("HeadlessChrome", rendered)

    def test_accept_cookies_uses_test_id_and_visible_text(self):
        from alditalk import accept_cookies

        page = Mock()
        test_id_locator = page.get_by_test_id.return_value
        text_filtered_locator = test_id_locator.filter.return_value

        accept_cookies(page)

        page.get_by_test_id.assert_called_once_with("uc-accept-all-button")
        test_id_locator.filter.assert_called_once_with(has_text="Alle akzeptieren")
        text_filtered_locator.wait_for.assert_called_once_with(state="visible")
        text_filtered_locator.click.assert_called_once_with()

    def test_usage_meter_ignores_100_and_clicks_button_below_3_5(self):
        from alditalk import check_usage_meter

        page = Mock()
        meter_locator = Mock()
        meter_locator.count.return_value = 2
        full_meter = Mock()
        full_meter.get_attribute.return_value = "100"
        low_meter = Mock()
        low_meter.get_attribute.return_value = "3.4"
        meter_locator.nth.side_effect = [full_meter, low_meter]
        button_locator = Mock()
        button_locator.first = Mock()
        page.locator.side_effect = [meter_locator, button_locator]

        check_usage_meter(page)

        page.locator.assert_any_call("svg.usage-meter__graph")
        full_meter.get_attribute.assert_called_once_with("aria-valuenow")
        low_meter.get_attribute.assert_called_once_with("aria-valuenow")
        button_locator.first.wait_for.assert_called_once_with(state="visible")
        button_locator.first.click.assert_called_once_with()

    def test_login_page_flow_logs_in_and_accepts_next_page_cookies(self):
        from alditalk import continue_to_login

        page = Mock()
        nav_locator = Mock()
        nav_text_locator = nav_locator.filter.return_value
        first_consent_locator = Mock()
        first_consent_text_locator = first_consent_locator.filter.return_value
        second_consent_locator = Mock()
        second_consent_text_locator = second_consent_locator.filter.return_value
        phone_locator = Mock()
        password_locator = Mock()
        login_locator = Mock()
        page.locator.side_effect = [
            nav_locator,
            phone_locator,
            password_locator,
            login_locator,
        ]
        page.get_by_test_id.side_effect = [
            first_consent_locator,
            second_consent_locator,
        ]
        second_consent_text_locator.is_visible.return_value = True
        page.url = "https://login.alditalk-kundenbetreuung.de/signin/"

        continue_to_login(page, "+491701234567", "secret")

        page.locator.assert_any_call("span.nav-service__text:visible")
        nav_locator.filter.assert_called_once_with(has_text="Mein ALDI TALK")
        nav_text_locator.wait_for.assert_called_once_with(state="visible")
        nav_text_locator.click.assert_called_once_with()
        page.wait_for_url.assert_called_once_with(
            "https://login.alditalk-kundenbetreuung.de/**"
        )
        page.locator.assert_any_call(
            'input.input__control[placeholder="Rufnummer"]'
        )
        page.locator.assert_any_call(
            "a.button.button--solid.button--medium.button--color-default."
            'button--has-label[href="#"]:visible'
        )
        phone_locator.wait_for.assert_called_once_with(state="visible")
        phone_locator.fill.assert_called_once_with("+491701234567")
        password_locator.wait_for.assert_called_once_with(state="visible")
        password_locator.fill.assert_called_once_with("secret")
        login_locator.wait_for.assert_called_once_with(state="visible")
        login_locator.click.assert_called_once_with()
        page.wait_for_load_state.assert_called_once_with("domcontentloaded")
        self.assertEqual(page.get_by_test_id.call_count, 2)
        first_consent_locator.filter.assert_called_once_with(
            has_text="Akzeptieren"
        )
        second_consent_locator.filter.assert_called_once_with(
            has_text="Akzeptieren"
        )
        first_consent_text_locator.wait_for.assert_called_once_with(state="visible")
        second_consent_text_locator.wait_for.assert_not_called()
        first_consent_text_locator.click.assert_called_once_with()
        second_consent_text_locator.click.assert_called_once_with()
        self.assertEqual(page.wait_for_timeout.call_count, 2)
        page.wait_for_timeout.assert_any_call(5000)

    def test_login_continues_when_overview_reloads_without_consent(self):
        from alditalk import continue_to_login

        page = Mock()
        nav_locator = Mock()
        first_consent_locator = Mock()
        second_consent_locator = Mock()
        second_consent_text_locator = second_consent_locator.filter.return_value
        phone_locator = Mock()
        password_locator = Mock()
        login_locator = Mock()
        page.locator.side_effect = [
            nav_locator,
            phone_locator,
            password_locator,
            login_locator,
        ]
        page.get_by_test_id.side_effect = [
            first_consent_locator,
            second_consent_locator,
        ]
        second_consent_text_locator.is_visible.return_value = False
        page.url = "https://www.alditalk-kundenportal.de/portal/auth/uebersicht/"

        continue_to_login(page, "+491701234567", "secret")

        second_consent_text_locator.click.assert_not_called()
        second_consent_text_locator.wait_for.assert_not_called()
        page.wait_for_load_state.assert_any_call("domcontentloaded", timeout=10000)
        page.wait_for_timeout.assert_any_call(1000)
        page.wait_for_timeout.assert_any_call(5000)

    def test_usage_meter_skips_non_numeric_values(self):
        from alditalk import check_usage_meter

        page = Mock()
        meter_locator = Mock()
        meter_locator.count.return_value = 1
        meter = Mock()
        meter.get_attribute.return_value = "3,4"
        meter_locator.nth.return_value = meter
        page.locator.return_value = meter_locator

        check_usage_meter(page)

        page.locator.assert_called_once_with("svg.usage-meter__graph")
        self.assertEqual(page.locator.call_count, 1)

    def test_usage_meter_stays_open_when_the_action_button_is_missing(self):
        from alditalk import check_usage_meter

        page = Mock()
        page.is_closed.return_value = False
        meter_locator = Mock()
        meter_locator.count.return_value = 1
        meter = Mock()
        meter.get_attribute.return_value = "1"
        meter_locator.nth.return_value = meter
        button_locator = Mock()
        button_locator.first.wait_for.side_effect = TimeoutError("button missing")
        page.locator.side_effect = [meter_locator, button_locator]

        check_usage_meter(page)

        button_locator.first.click.assert_not_called()

    def test_monitor_page_keeps_refreshing_when_expected_text_is_missing(self):
        from alditalk import monitor_page

        page = Mock()
        page.locator.return_value.count.return_value = 0
        page.get_by_text.return_value.count.return_value = 0
        screenshots = {"n": 0}

        def is_closed():
            return screenshots["n"] >= 2

        def screenshot(path, full_page=False):
            screenshots["n"] += 1
            self.assertTrue(path.endswith(".png"))
            self.assertIn("alditalk-unexpected-", path)
            self.assertTrue(full_page)

        page.is_closed.side_effect = is_closed
        page.screenshot.side_effect = screenshot
        delay_arguments = []

        def fixed_delay(minimum, maximum):
            delay_arguments.append((minimum, maximum))
            return 42

        browser = Mock()
        browser.is_connected.return_value = True

        with tempfile.TemporaryDirectory() as directory:
            monitor_page(
                page,
                "+491701234567",
                "secret",
                random_delay=fixed_delay,
                delay_minimum=30,
                delay_maximum=90,
                screenshot_dir=Path(directory),
                browser=browser,
            )

        self.assertEqual(screenshots["n"], 2)
        self.assertEqual(page.wait_for_timeout.call_count, 2)
        page.wait_for_timeout.assert_called_with(42000)
        self.assertEqual(delay_arguments, [(30, 90), (30, 90)])
        self.assertEqual(page.reload.call_count, 2)
        page.reload.assert_called_with(wait_until="domcontentloaded")
        browser.close.assert_not_called()

    def test_monitor_page_relogs_in_after_session_expiry(self):
        from alditalk import monitor_page

        page = Mock()
        page.get_by_text.side_effect = [
            Mock(count=Mock(return_value=1)),
            Mock(count=Mock(return_value=0)),
            Mock(count=Mock(return_value=0)),
            Mock(count=Mock(return_value=0)),
        ]
        phone_locator = Mock()
        password_locator = Mock()
        login_locator = Mock()
        meter_locator = Mock()
        meter_locator.count.return_value = 0
        page.locator.side_effect = [
            phone_locator,
            password_locator,
            login_locator,
            meter_locator,
        ]
        page.is_closed.side_effect = lambda: page.screenshot.called
        browser = Mock()
        browser.is_connected.return_value = True

        with tempfile.TemporaryDirectory() as directory:
            monitor_page(
                page,
                "+491701234567",
                "secret",
                random_delay=lambda minimum, maximum: 42,
                screenshot_dir=Path(directory),
                browser=browser,
            )

        phone_locator.fill.assert_called_once_with("+491701234567")
        password_locator.fill.assert_called_once_with("secret")
        login_locator.click.assert_called_once_with()
        page.wait_for_load_state.assert_called_once_with("domcontentloaded")
        page.screenshot.assert_called_once()
        browser.close.assert_not_called()

    def test_monitor_page_retries_reload_failures_until_the_browser_disconnects(self):
        from alditalk import monitor_page

        page = Mock()
        page.is_closed.return_value = False
        browser = Mock()
        browser.is_connected.return_value = True
        reloads = {"n": 0}

        def reload(wait_until):
            reloads["n"] += 1
            if reloads["n"] >= 2:
                browser.is_connected.return_value = False
            raise TimeoutError("Navigation timeout")

        page.reload.side_effect = reload

        monitor_page(
            page,
            "+491701234567",
            "secret",
            random_delay=lambda minimum, maximum: 1,
            browser=browser,
        )

        self.assertEqual(reloads["n"], 2)
        browser.close.assert_not_called()

    def test_monitor_page_returns_on_renderer_crash_without_closing_the_browser(self):
        from alditalk import monitor_page

        page = Mock()
        page.is_closed.return_value = False
        page.reload.side_effect = RuntimeError("Page crashed")
        browser = Mock()
        browser.is_connected.return_value = True

        monitor_page(
            page,
            "+491701234567",
            "secret",
            random_delay=lambda minimum, maximum: 1,
            browser=browser,
        )

        page.reload.assert_called_once()
        browser.close.assert_not_called()
        page.close.assert_not_called()

    def test_monitor_page_continues_when_relogin_fails(self):
        from alditalk import monitor_page

        page = Mock()
        page.is_closed.return_value = False
        browser = Mock()
        browser.is_connected.return_value = True
        reloads = {"n": 0}
        phone_locator = Mock()

        def wait_for(state):
            raise TimeoutError("phone field missing")

        phone_locator.wait_for.side_effect = wait_for

        def reload(wait_until):
            reloads["n"] += 1
            if reloads["n"] >= 2:
                browser.is_connected.return_value = False
                raise RuntimeError("Connection closed while reading from the driver")

        def get_by_text(text, exact=False):
            found = Mock()
            found.count.return_value = 1 if "Sitzung" in text else 0
            return found

        page.reload.side_effect = reload
        page.get_by_text.side_effect = get_by_text
        page.locator.return_value = phone_locator

        monitor_page(
            page,
            "+491701234567",
            "secret",
            random_delay=lambda minimum, maximum: 1,
            browser=browser,
        )

        self.assertEqual(reloads["n"], 2)
        phone_locator.wait_for.assert_called_once_with(state="visible")
        browser.close.assert_not_called()

    def test_hold_browser_open_retries_sign_in_until_the_window_closes(self):
        from alditalk import hold_browser_open

        browser = Mock()
        browser.is_connected.return_value = True
        context = Mock()
        page = Mock()
        page.is_closed.return_value = False
        attempts = {"n": 0}

        def sign_in(active_page, phonenumber, password):
            attempts["n"] += 1
            if attempts["n"] >= 2:
                browser.is_connected.return_value = False
            raise TimeoutError("consent button missing")

        with patch("alditalk.sign_in", side_effect=sign_in):
            hold_browser_open(
                browser,
                context,
                page,
                "+491701234567",
                "secret",
                30,
                90,
            )

        self.assertEqual(attempts["n"], 2)
        browser.close.assert_not_called()
        context.close.assert_not_called()
        page.close.assert_not_called()

    def test_hold_browser_open_replaces_a_crashed_tab(self):
        from alditalk import hold_browser_open

        browser = Mock()
        browser.is_connected.return_value = True
        context = Mock()
        page = Mock()
        page.is_closed.return_value = False
        replacement = Mock()
        replacement.is_closed.return_value = False
        context.new_page.return_value = replacement
        seen = []

        def sign_in(active_page, phonenumber, password):
            seen.append(active_page)
            if active_page is replacement:
                browser.is_connected.return_value = False
                return None
            raise RuntimeError("Page crashed")

        with patch("alditalk.sign_in", side_effect=sign_in):
            hold_browser_open(
                browser, context, page, "+491701234567", "secret", 30, 90
            )

        self.assertEqual(seen, [page, replacement])
        context.new_page.assert_called_once_with()
        page.close.assert_called_once_with()
        browser.close.assert_not_called()
        context.close.assert_not_called()

    def test_run_leaves_the_browser_open(self):
        from alditalk import run

        browser = Mock()
        browser.is_connected.return_value = False
        context = Mock()
        page = Mock()
        page.is_closed.return_value = True
        browser.new_context.return_value = context
        context.new_page.return_value = page
        playwright = Mock()
        playwright.chromium.launch.return_value = browser
        playwright.devices = {
            "Desktop Chrome": {
                "viewport": {"width": 1280, "height": 720},
                "user_agent": "Mozilla/5.0 HeadlessChrome",
            }
        }
        manager = Mock()
        manager.__enter__ = Mock(return_value=playwright)
        manager.__exit__ = Mock(return_value=False)

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.yaml"
            config_path.write_text(
                "phonenumber: '+491701234567'\npassword: 'secret'\n"
                "headless: true\ndelay-minimum: 30\ndelay-maximum: 90\n",
                encoding="utf-8",
            )
            with patch("playwright.sync_api.sync_playwright", return_value=manager):
                run(config_path)

        browser.close.assert_not_called()
        context.close.assert_not_called()
        page.close.assert_not_called()

    def test_a_closed_tab_is_not_treated_as_the_browser_closing(self):
        from alditalk import browser_disconnected, page_needs_replacement

        browser = Mock()
        browser.is_connected.return_value = True
        page = Mock()
        page.is_closed.return_value = True
        closed_tab = RuntimeError(
            "Target page, context or browser has been closed"
        )
        driver_died = RuntimeError(
            "Connection closed while reading from the driver"
        )

        self.assertFalse(browser_disconnected(browser, closed_tab))
        self.assertTrue(page_needs_replacement(page, closed_tab))
        self.assertFalse(browser_disconnected(browser, driver_died))
        self.assertTrue(page_needs_replacement(page, RuntimeError("Page crashed")))

        browser.is_connected.return_value = False
        self.assertTrue(browser_disconnected(browser, closed_tab))
        browser.is_connected.side_effect = RuntimeError("driver gone")
        self.assertTrue(browser_disconnected(browser))

    def test_safe_error_omits_the_playwright_call_log(self):
        from alditalk import safe_error

        exc = RuntimeError(
            'Timeout 30000ms exceeded.\nCall log:\n  - fill("secret")'
        )

        summary = safe_error(exc)

        self.assertEqual(summary, "RuntimeError: Timeout 30000ms exceeded.")
        self.assertNotIn("secret", summary)

    def test_unexpected_screenshots_keep_only_the_latest(self):
        from alditalk import monitor_page

        page = Mock()
        page.locator.return_value.count.return_value = 0
        page.get_by_text.return_value.count.return_value = 0
        page.is_closed.side_effect = lambda: page.screenshot.call_count >= 2
        browser = Mock()
        browser.is_connected.return_value = True

        def screenshot(path, full_page=False):
            Path(path).write_bytes(b"png")

        page.screenshot.side_effect = screenshot

        with tempfile.TemporaryDirectory() as directory:
            screenshot_dir = Path(directory)
            (screenshot_dir / "alditalk-unexpected-old.png").write_bytes(b"old")
            monitor_page(
                page,
                "+491701234567",
                "secret",
                random_delay=lambda minimum, maximum: 1,
                screenshot_dir=screenshot_dir,
                browser=browser,
            )
            saved = list(screenshot_dir.glob("alditalk-unexpected-*.png"))

        self.assertEqual(len(saved), 1)
        self.assertNotEqual(saved[0].name, "alditalk-unexpected-old.png")

    def test_run_restarts_the_session_while_the_browser_is_connected(self):
        from alditalk import run

        browser = Mock()
        browser.is_connected.return_value = True
        context = Mock()
        page = Mock()
        page.is_closed.return_value = False
        calls = {"context": 0, "hold": 0}

        def new_context(**kwargs):
            calls["context"] += 1
            if calls["context"] == 1:
                raise RuntimeError('context failed\nCall log:\n  - fill("secret")')
            return context

        def hold(*args, **kwargs):
            calls["hold"] += 1
            if calls["hold"] >= 2:
                browser.is_connected.return_value = False

        browser.new_context.side_effect = new_context
        context.new_page.return_value = page
        playwright = Mock()
        playwright.chromium.launch.return_value = browser
        playwright.devices = {"Desktop Chrome": {"viewport": {"width": 1280, "height": 720}}}
        manager = Mock()
        manager.__enter__ = Mock(return_value=playwright)
        manager.__exit__ = Mock(return_value=False)

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.yaml"
            config_path.write_text(
                "phonenumber: '+491701234567'\npassword: 'secret'\n"
                "headless: true\ndelay-minimum: 30\ndelay-maximum: 90\n",
                encoding="utf-8",
            )
            with (
                patch("playwright.sync_api.sync_playwright", return_value=manager),
                patch("alditalk.hold_browser_open", side_effect=hold),
                patch("alditalk.time.sleep") as sleep,
            ):
                run(config_path)

        self.assertEqual(calls["context"], 2)
        self.assertEqual(calls["hold"], 2)
        sleep.assert_called()
        browser.close.assert_not_called()
        context.close.assert_not_called()
        page.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
