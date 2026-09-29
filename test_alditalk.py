import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


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
        second_consent_text_locator.wait_for.assert_called_once_with(
            state="visible"
        )
        first_consent_text_locator.click.assert_called_once_with()
        second_consent_text_locator.click.assert_called_once_with()
        self.assertEqual(page.wait_for_timeout.call_count, 2)
        page.wait_for_timeout.assert_any_call(5000)

    def test_monitor_page_refreshes_and_screenshots_when_expected_text_is_missing(self):
        from alditalk import monitor_page

        page = Mock()
        page.locator.return_value.count.return_value = 0
        page.get_by_text.side_effect = [
            Mock(count=Mock(return_value=0)),
            Mock(count=Mock(return_value=1)),
            Mock(count=Mock(return_value=0)),
        ]
        delay_arguments = []

        def fixed_delay(minimum, maximum):
            delay_arguments.append((minimum, maximum))
            return 42

        with tempfile.TemporaryDirectory() as directory:
            screenshot_path = monitor_page(
                page,
                "+491701234567",
                "secret",
                random_delay=fixed_delay,
                delay_minimum=30,
                delay_maximum=90,
                screenshot_dir=Path(directory),
            )

            self.assertTrue(screenshot_path.parent == Path(directory))
            self.assertTrue(screenshot_path.name.startswith("alditalk-unexpected-"))
            page.wait_for_timeout.assert_called_once_with(42000)
            self.assertEqual(delay_arguments, [(30, 90)])
            page.reload.assert_called_once_with(wait_until="domcontentloaded")
            page.screenshot.assert_called_once()

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

        with tempfile.TemporaryDirectory() as directory:
            screenshot_path = monitor_page(
                page,
                "+491701234567",
                "secret",
                random_delay=lambda minimum, maximum: 42,
                screenshot_dir=Path(directory),
            )

        phone_locator.fill.assert_called_once_with("+491701234567")
        password_locator.fill.assert_called_once_with("secret")
        login_locator.click.assert_called_once_with()
        page.wait_for_load_state.assert_called_once_with("domcontentloaded")
        self.assertTrue(screenshot_path.exists() is False)


if __name__ == "__main__":
    unittest.main()
