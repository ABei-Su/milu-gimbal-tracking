"""The SDK listener must be removed independently in each process."""

import types
import unittest
from unittest.mock import Mock, patch
from milu import maixcam2


class CommOwnershipTests(unittest.TestCase):
    def test_release_calls_official_api(self):
        remove = Mock(return_value=True)
        sdk = types.SimpleNamespace(comm=types.SimpleNamespace(rm_default_comm_listener=remove))
        with patch.dict("sys.modules", {"maix": sdk}):
            maixcam2.release_default_listener()
        remove.assert_called_once_with()

    def test_sdk_failure_propagates(self):
        remove = Mock(side_effect=RuntimeError("release failed"))
        sdk = types.SimpleNamespace(comm=types.SimpleNamespace(rm_default_comm_listener=remove))
        with (
            patch.dict("sys.modules", {"maix": sdk}),
            self.assertRaisesRegex(RuntimeError, "release failed"),
        ):
            maixcam2.release_default_listener()

    def test_missing_api_stops_with_actionable_error(self):
        sdk = types.SimpleNamespace(comm=types.SimpleNamespace())
        with (
            patch.dict("sys.modules", {"maix": sdk}),
            self.assertRaisesRegex(RuntimeError, "COMM_RELEASE_UNAVAILABLE"),
        ):
            maixcam2.release_default_listener()

    def test_unconfirmed_release_blocks_startup(self):
        sdk = types.SimpleNamespace(
            comm=types.SimpleNamespace(rm_default_comm_listener=lambda: False)
        )
        with (
            patch.dict("sys.modules", {"maix": sdk}),
            self.assertRaisesRegex(RuntimeError, "COMM_RELEASE_UNCONFIRMED"),
        ):
            maixcam2.release_default_listener()
