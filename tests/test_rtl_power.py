from __future__ import annotations

import unittest
from unittest.mock import patch

from freewili_foxhunt.models import FrequencyEntry
from freewili_foxhunt.rtl_power import RtlPowerStream


class RtlPowerTests(unittest.TestCase):
    @patch("freewili_foxhunt.rtl_power.shutil.which", return_value="/usr/bin/rtl_power")
    def test_command_is_centered_and_bounded(self, _which) -> None:
        stream = RtlPowerStream()
        command = stream.command_for(FrequencyEntry(145_265_000, "fox", 200_000))
        self.assertIn("145165000:145365000:833", command)
        self.assertEqual(command[-1], "/dev/stdout")


if __name__ == "__main__":
    unittest.main()
