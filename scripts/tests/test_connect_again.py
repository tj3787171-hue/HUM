import unittest
from unittest.mock import patch

from scripts import connect_again


class ConnectAgainTests(unittest.TestCase):
    def test_connect_again_retries_then_succeeds(self) -> None:
        responses = [
            (1, "RemoteDisconnected: peer closed"),
            (1, "URLError: timeout"),
            (200, "OK"),
        ]

        with patch("scripts.connect_again.check", side_effect=responses) as mocked_check:
            with patch("scripts.connect_again.time.sleep") as mocked_sleep:
                status, reason, attempts = connect_again.connect_again(
                    "http://example.com",
                    retries=4,
                    delay_seconds=0.1,
                    timeout=5,
                )

        self.assertEqual((status, reason, attempts), (200, "OK", 3))
        self.assertEqual(mocked_check.call_count, 3)
        self.assertEqual(mocked_sleep.call_count, 2)

    def test_connect_again_stops_without_retry_for_404(self) -> None:
        with patch("scripts.connect_again.check", return_value=(404, "Not Found")) as mocked_check:
            with patch("scripts.connect_again.time.sleep") as mocked_sleep:
                status, reason, attempts = connect_again.connect_again(
                    "http://example.com/missing",
                    retries=5,
                    delay_seconds=0.1,
                )

        self.assertEqual((status, reason, attempts), (404, "Not Found", 1))
        self.assertEqual(mocked_check.call_count, 1)
        self.assertEqual(mocked_sleep.call_count, 0)


if __name__ == "__main__":
    unittest.main()
