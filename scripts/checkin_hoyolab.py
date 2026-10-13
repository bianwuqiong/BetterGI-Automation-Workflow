"""HoYoLAB daily check-in client for Genshin Impact.

Standard library only. Designed to run as a preflight step before game launch so
that daily check-in rewards arrive in the in-game mailbox in time for the
in-game '领取邮件' task.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

try:
    from .hoyolab_credentials import CredentialError, load_cookie, validate_cookie
except ImportError:
    from hoyolab_credentials import CredentialError, load_cookie, validate_cookie

DEFAULT_ACT_ID = "e202102251931481"
DEFAULT_TIMEOUT_SEC = 15
DEFAULT_RETRY_COUNT = 2

INFO_URL = "https://sg-hk4e-api.hoyolab.com/event/sol/info"
SIGN_URL = "https://sg-hk4e-api.hoyolab.com/event/sol/sign"
HOME_URL = "https://sg-hk4e-api.hoyolab.com/event/sol/home"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Referer": "https://act.hoyolab.com/",
    "Origin": "https://act.hoyolab.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/json;charset=utf-8",
}


def mask_cookie_account(cookie: str) -> str:
    """Return a masked identifier from cookie for safe logging (never outputs secrets)."""
    if not cookie:
        return "none"
    match = re.search(r'(?:ltuid_v2|ltuid|account_id_v2|account_id)=(\d+)', cookie)
    if match:
        uid = match.group(1)
        if len(uid) > 4:
            return f"{uid[:2]}***{uid[-2:]}"
        return "***"
    return "configured"


def normalize_cookie(cookie: Any) -> str:
    """Normalize cookie dict or string into a single cookie header string."""
    if isinstance(cookie, dict):
        return "; ".join(f"{k.strip()}={v.strip()}" for k, v in cookie.items())
    if isinstance(cookie, str):
        return cookie.strip()
    return ""


def request_json(url: str, data: dict[str, Any] | None = None,
                 cookie: str = "", timeout: int = DEFAULT_TIMEOUT_SEC) -> tuple[dict[str, Any] | None, str | None]:
    """Execute HTTP request using urllib.request and return (parsed_json, error_message)."""
    headers = dict(DEFAULT_HEADERS)
    if cookie:
        try:
            headers["Cookie"] = validate_cookie(cookie)
        except CredentialError:
            return None, "Cookie 格式无效"

    body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST" if data is not None else "GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(payload)
            if not isinstance(parsed, dict):
                return None, f"非法的 JSON 响应类型: {type(parsed)}"
            return parsed, None
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
            err_json = json.loads(err_body)
            if isinstance(err_json, dict) and "retcode" in err_json:
                return err_json, None
        except Exception:
            pass
        return None, f"HTTP 错误 {exc.code}"
    except urllib.error.URLError as exc:
        return None, "网络连接失败"
    except TimeoutError:
        return None, f"请求超时 ({timeout}s)"
    except json.JSONDecodeError as exc:
        return None, "JSON 解析失败"
    except Exception as exc:
        return None, "请求异常"


def fetch_checkin_info(cookie: str, act_id: str = DEFAULT_ACT_ID,
                       timeout: int = DEFAULT_TIMEOUT_SEC) -> tuple[dict[str, Any] | None, str | None]:
    """Query current check-in status (is_sign, total_sign_day, today)."""
    url = f"{INFO_URL}?act_id={urllib.parse.quote(act_id)}"
    return request_json(url, cookie=cookie, timeout=timeout)


def submit_checkin(cookie: str, act_id: str = DEFAULT_ACT_ID,
                   timeout: int = DEFAULT_TIMEOUT_SEC) -> tuple[dict[str, Any] | None, str | None]:
    """Submit daily check-in."""
    payload = {"act_id": act_id}
    return request_json(SIGN_URL, data=payload, cookie=cookie, timeout=timeout)


def fetch_award_name(act_id: str = DEFAULT_ACT_ID, day_index: int = 1,
                     timeout: int = DEFAULT_TIMEOUT_SEC) -> str | None:
    """Optionally query reward list to resolve the reward name for today."""
    url = f"{HOME_URL}?act_id={urllib.parse.quote(act_id)}"
    data, err = request_json(url, timeout=timeout)
    if not isinstance(data, dict) or type(data.get("retcode")) is not int or data["retcode"] != 0:
        return None
    payload = data.get("data")
    if not isinstance(payload, dict):
        return None
    awards = payload.get("awards", [])
    if isinstance(awards, list) and 1 <= day_index <= len(awards):
        award = awards[day_index - 1]
        if not isinstance(award, dict):
            return None
        name = award.get("name")
        cnt = award.get("cnt")
        if name and cnt:
            return f"{name} x{cnt}"
        if name:
            return str(name)
    return None


def valid_info_data(data: Any) -> bool:
    return (isinstance(data, dict) and type(data.get('is_sign')) is bool
            and type(data.get('total_sign_day')) is int and data['total_sign_day'] >= 0)

def execute_hoyolab_checkin(root: Path | str, config_path: Path | str | None = None,
                            dry_run: bool = False) -> dict[str, Any]:
    """Main programmatic entrance for checking in to HoYoLAB.

    Returns a structured dictionary safe for logging and inclusion in result.json.
    """
    root_path = Path(root).resolve()
    cfg_file = Path(config_path) if config_path else root_path / "config/hoyolab.json"

    started_at = time.time()
    result: dict[str, Any] = {
        "enabled": False,
        "status": "unconfigured",
        "message": "未配置 HoYoLAB 签到",
        "totalSignDays": None,
        "signedToday": False,
        "reward": None,
        "account": "none",
        "warning": None,
        "elapsedSec": 0.0,
        "statusVerified": False,
        "submissionAttempted": False,
        "today": None,
    }

    if not cfg_file.is_file():
        result["elapsedSec"] = round(time.time() - started_at, 3)
        return result

    try:
        with cfg_file.open(encoding="utf-8-sig") as stream:
            config = json.load(stream)
    except Exception as exc:
        result.update(
            enabled=False,
            status="warning",
            message="读取 config/hoyolab.json 失败",
            warning="读取 HoYoLAB 配置文件失败",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    if not isinstance(config, dict) or not config.get("enabled", True):
        result.update(
            enabled=False,
            status="skipped",
            message="HoYoLAB 签到已在配置中禁用",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    try:
        cookie_str = load_cookie(config)
    except CredentialError:
        result.update(
            enabled=True,
            status="warning",
            message="Cookie 为空或本机凭据不可用",
            warning="Cookie 为空、格式无效或本机凭据解密失败，请在本机重新配置",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    act_id = str(config.get("actId") or DEFAULT_ACT_ID).strip()
    try:
        timeout = min(60, max(1, int(config.get("timeoutSec") or DEFAULT_TIMEOUT_SEC)))
        retry_count = min(5, max(1, int(config.get("retryCount") or DEFAULT_RETRY_COUNT)))
    except (TypeError, ValueError, OverflowError):
        result.update(enabled=True, status="warning", warning="签到请求配置无效", message="签到请求配置无效")
        return result

    account_id = mask_cookie_account(cookie_str)
    result.update(enabled=True, account=account_id)

    # 1. Query info first
    info_resp: dict[str, Any] | None = None
    info_err: str | None = None
    for attempt in range(retry_count):
        info_resp, info_err = fetch_checkin_info(cookie_str, act_id=act_id, timeout=timeout)
        if info_resp is not None or attempt == retry_count - 1:
            break
        time.sleep(1)

    if info_err or not info_resp:
        result.update(
            status="warning",
            message="查询签到状态失败",
            warning="查询 HoYoLAB 签到状态失败",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    retcode = info_resp.get("retcode")
    if retcode == -100:
        result.update(
            status="warning",
            message="Cookie 已失效",
            warning="HoYoLAB Cookie 已失效或未登录 (-100)，请更新 config/hoyolab.json",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result
    if type(retcode) is not int or retcode != 0:
        result.update(
            status="warning",
            message="签到状态接口异常",
            warning="HoYoLAB 签到状态接口异常",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    info_data = info_resp.get("data")
    if not valid_info_data(info_data):
        result.update(status="warning", message="签到状态数据无效", warning="签到状态数据无效")
        return result
    is_signed = info_data['is_sign']
    total_days = info_data['total_sign_day']
    result.update(statusVerified=True, today=info_data.get('today') if isinstance(info_data.get('today'), str) else None)
    result["totalSignDays"] = total_days
    result["signedToday"] = is_signed

    if dry_run:
        result.update(
            status="planned",
            message=f"预览完成；今日状态: {'已签到' if is_signed else '未签到'}，累计 {total_days} 天",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    if is_signed:
        result.update(
            status="already_signed",
            message=f"今日已完成签到 (累计 {total_days} 天)",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    # Submit once: a lost response can mean the server accepted the action.
    result.update(submissionAttempted=True, statusVerified=False)
    sign_resp, sign_err = submit_checkin(cookie_str, act_id=act_id, timeout=timeout)
    sign_retcode = sign_resp.get('retcode') if isinstance(sign_resp, dict) else None
    if type(sign_retcode) is not int:
        sign_retcode = None
    if sign_retcode == 1034:
        result.update(status='warning', message='触发人机验证', warning='HoYoLAB 签到触发人机验证，请在官方网页完成验证', elapsedSec=round(time.time() - started_at, 3))
        return result
    if sign_retcode == -100:
        result.update(status='warning', message='Cookie 已失效', warning='Cookie 已失效，请在本机重新配置', elapsedSec=round(time.time() - started_at, 3))
        return result
    if sign_retcode not in (0, -5003, None):
        result.update(status='warning', message='签到提交接口异常', warning='签到提交接口异常', elapsedSec=round(time.time() - started_at, 3))
        return result
    verified = None
    for attempt in range(retry_count):
        response, error = fetch_checkin_info(cookie_str, act_id=act_id, timeout=timeout)
        if isinstance(response, dict) and type(response.get('retcode')) is int and response['retcode'] == 0 and valid_info_data(response.get('data')):
            verified = response['data']
            break
        if attempt < retry_count - 1:
            time.sleep(1)
    if verified is not None:
        result.update(statusVerified=True, signedToday=verified['is_sign'], totalSignDays=verified['total_sign_day'], today=verified.get('today') if isinstance(verified.get('today'), str) else None)
    if verified is not None and verified['is_sign']:
        award = fetch_award_name(act_id=act_id, day_index=verified['total_sign_day'], timeout=timeout)
        result.update(status='already_signed' if sign_retcode == -5003 else 'success', reward=award, message=f"签到状态已回读确认，累计 {verified['total_sign_day']} 天", elapsedSec=round(time.time() - started_at, 3))
    else:
        result.update(status='warning', message='提交后未确认今日签到成功', warning='提交后未确认今日签到成功；未再次提交，请在官方网页检查', elapsedSec=round(time.time() - started_at, 3))
    return result

def main():
    parser = argparse.ArgumentParser(description="HoYoLAB Genshin Impact daily check-in utility.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                        help="Root directory of the project.")
    parser.add_argument("--config", default=None, help="Custom path to hoyolab.json.")
    parser.add_argument("--status", action="store_true", help="Only check current check-in status.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without submitting check-in.")
    args = parser.parse_args()

    res = execute_hoyolab_checkin(args.root, config_path=args.config, dry_run=(args.dry_run or args.status))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res.get("status") == "warning":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
