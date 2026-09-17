"""Unit tests for HoYoLAB daily check-in client."""
from __future__ import annotations

import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from scripts import checkin_hoyolab


class CheckinHoyolabTests(unittest.TestCase):
    def test_mask_cookie_account(self):
        self.assertEqual(checkin_hoyolab.mask_cookie_account(""), "none")
        self.assertEqual(
            checkin_hoyolab.mask_cookie_account("ltuid_v2=12345678; ltoken_v2=secret;"),
            "12***78"
        )
        self.assertEqual(
            checkin_hoyolab.mask_cookie_account("account_id=987654321; other=1"),
            "98***21"
        )
        self.assertEqual(
            checkin_hoyolab.mask_cookie_account("foo=bar; baz=qux"),
            "configured"
        )

    def test_normalize_cookie(self):
        self.assertEqual(
            checkin_hoyolab.normalize_cookie({"ltoken_v2": "v2_xyz", "ltuid_v2": "123"}),
            "ltoken_v2=v2_xyz; ltuid_v2=123"
        )
        self.assertEqual(
            checkin_hoyolab.normalize_cookie("  a=1; b=2  "),
            "a=1; b=2"
        )
        self.assertEqual(checkin_hoyolab.normalize_cookie(None), "")

    def test_unconfigured_when_config_absent(self):
        result = checkin_hoyolab.execute_hoyolab_checkin("/non/existent/path")
        self.assertFalse(result["enabled"])
        self.assertEqual(result["status"], "unconfigured")
        self.assertIsNone(result["warning"])

    def test_skipped_when_disabled_in_config(self, tmp_path=None):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "hoyolab.json"
            cfg.write_text(json.dumps({"enabled": False, "cookie": "abc"}), encoding="utf-8")
            result = checkin_hoyolab.execute_hoyolab_checkin(td, config_path=cfg)
            self.assertFalse(result["enabled"])
            self.assertEqual(result["status"], "skipped")
            self.assertIsNone(result["warning"])

    def test_warning_when_cookie_empty(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "hoyolab.json"
            cfg.write_text(json.dumps({"enabled": True, "cookie": ""}), encoding="utf-8")
            result = checkin_hoyolab.execute_hoyolab_checkin(td, config_path=cfg)
            self.assertTrue(result["enabled"])
            self.assertEqual(result["status"], "warning")
            self.assertIn("Cookie 为空", result["warning"])

    def test_already_signed_skips_post(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "hoyolab.json"
            cfg.write_text(json.dumps({"enabled": True, "cookie": "ltuid_v2=123456; ltoken_v2=secret"}), encoding="utf-8")

            info_resp = {
                "retcode": 0,
                "message": "OK",
                "data": {"is_sign": True, "total_sign_day": 12, "today": "2026-09-16"}
            }

            with patch.object(checkin_hoyolab, "fetch_checkin_info", return_value=(info_resp, None)) as mock_info, \
                 patch.object(checkin_hoyolab, "submit_checkin") as mock_sign:
                result = checkin_hoyolab.execute_hoyolab_checkin(td, config_path=cfg)

            self.assertEqual(result["status"], "already_signed")
            self.assertTrue(result["signedToday"])
            self.assertEqual(result["totalSignDays"], 12)
            self.assertIsNone(result["warning"])
            mock_info.assert_called_once()
            mock_sign.assert_not_called()

    def test_dry_run_inspects_without_signing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "hoyolab.json"
            cfg.write_text(json.dumps({"enabled": True, "cookie": "ltuid_v2=123456; ltoken_v2=secret"}), encoding="utf-8")

            info_resp = {
                "retcode": 0,
                "message": "OK",
                "data": {"is_sign": False, "total_sign_day": 5, "today": "2026-09-16"}
            }

            with patch.object(checkin_hoyolab, "fetch_checkin_info", return_value=(info_resp, None)) as mock_info, \
                 patch.object(checkin_hoyolab, "submit_checkin") as mock_sign:
                result = checkin_hoyolab.execute_hoyolab_checkin(td, config_path=cfg, dry_run=True)

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["signedToday"])
            self.assertEqual(result["totalSignDays"], 5)
            mock_info.assert_called_once()
            mock_sign.assert_not_called()

    def test_first_sign_success(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "hoyolab.json"
            cfg.write_text(json.dumps({"enabled": True, "cookie": "ltuid_v2=123456; ltoken_v2=secret"}), encoding="utf-8")

            info_resp = {
                "retcode": 0,
                "message": "OK",
                "data": {"is_sign": False, "total_sign_day": 5, "today": "2026-09-16"}
            }
            sign_resp = {
                "retcode": 0,
                "message": "OK",
                "data": {"code": "ok"}
            }

            with patch.object(checkin_hoyolab, "fetch_checkin_info", return_value=(info_resp, None)), \
                 patch.object(checkin_hoyolab, "submit_checkin", return_value=(sign_resp, None)), \
                 patch.object(checkin_hoyolab, "fetch_award_name", return_value="原石 x20"):
                result = checkin_hoyolab.execute_hoyolab_checkin(td, config_path=cfg)

            self.assertEqual(result["status"], "success")
            self.assertTrue(result["signedToday"])
            self.assertEqual(result["totalSignDays"], 6)
            self.assertEqual(result["reward"], "原石 x20")
            self.assertIsNone(result["warning"])

    def test_sign_returns_already_signed_retcode(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "hoyolab.json"
            cfg.write_text(json.dumps({"enabled": True, "cookie": "ltuid_v2=123456; ltoken_v2=secret"}), encoding="utf-8")

            info_resp = {
                "retcode": 0,
                "message": "OK",
                "data": {"is_sign": False, "total_sign_day": 5, "today": "2026-09-16"}
            }
            sign_resp = {
                "retcode": -5003,
                "message": "OK",
            }

            with patch.object(checkin_hoyolab, "fetch_checkin_info", return_value=(info_resp, None)), \
                 patch.object(checkin_hoyolab, "submit_checkin", return_value=(sign_resp, None)):
                result = checkin_hoyolab.execute_hoyolab_checkin(td, config_path=cfg)

            self.assertEqual(result["status"], "already_signed")
            self.assertTrue(result["signedToday"])
            self.assertEqual(result["totalSignDays"], 5)
            self.assertIsNone(result["warning"])

    def test_cookie_expired_fails_open_with_warning(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "hoyolab.json"
            cfg.write_text(json.dumps({"enabled": True, "cookie": "ltuid_v2=123456; ltoken_v2=expired"}), encoding="utf-8")

            info_resp = {
                "retcode": -100,
                "message": "Not logged in",
            }

            with patch.object(checkin_hoyolab, "fetch_checkin_info", return_value=(info_resp, None)):
                result = checkin_hoyolab.execute_hoyolab_checkin(td, config_path=cfg)

            self.assertEqual(result["status"], "warning")
            self.assertIn("Cookie 已失效", result["warning"])

    def test_captcha_triggered_fails_open_with_warning(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "hoyolab.json"
            cfg.write_text(json.dumps({"enabled": True, "cookie": "ltuid_v2=123456; ltoken_v2=secret"}), encoding="utf-8")

            info_resp = {
                "retcode": 0,
                "message": "OK",
                "data": {"is_sign": False, "total_sign_day": 5, "today": "2026-09-16"}
            }
            sign_resp = {
                "retcode": 1034,
                "message": "risk control",
            }

            with patch.object(checkin_hoyolab, "fetch_checkin_info", return_value=(info_resp, None)), \
                 patch.object(checkin_hoyolab, "submit_checkin", return_value=(sign_resp, None)):
                result = checkin_hoyolab.execute_hoyolab_checkin(td, config_path=cfg)

            self.assertEqual(result["status"], "warning")
            self.assertIn("人机验证", result["warning"])

    def test_network_failure_fails_open_with_warning(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "hoyolab.json"
            cfg.write_text(json.dumps({"enabled": True, "cookie": "ltuid_v2=123456; ltoken_v2=secret"}), encoding="utf-8")

            with patch.object(checkin_hoyolab, "fetch_checkin_info", return_value=(None, "网络连接失败: timed out")):
                result = checkin_hoyolab.execute_hoyolab_checkin(td, config_path=cfg)

            self.assertEqual(result["status"], "warning")
            self.assertIn("网络连接失败", result["warning"])


if __name__ == "__main__":
    unittest.main()
