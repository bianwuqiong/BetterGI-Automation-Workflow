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
        headers["Cookie"] = cookie

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
        return None, f"HTTP 错误 {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return None, f"网络连接失败: {exc.reason}"
    except TimeoutError:
        return None, f"请求超时 ({timeout}s)"
    except json.JSONDecodeError as exc:
        return None, f"JSON 解析失败: {exc}"
    except Exception as exc:
        return None, f"请求异常: {exc}"


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
    if not data or data.get("retcode") != 0:
        return None
    awards = data.get("data", {}).get("awards", [])
    if isinstance(awards, list) and 1 <= day_index <= len(awards):
        award = awards[day_index - 1]
        name = award.get("name")
        cnt = award.get("cnt")
        if name and cnt:
            return f"{name} x{cnt}"
        if name:
            return str(name)
    return None


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
            warning=f"读取 HoYoLAB 配置文件失败: {exc}",
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

    cookie_str = normalize_cookie(config.get("cookie"))
    if not cookie_str:
        result.update(
            enabled=True,
            status="warning",
            message="Cookie 为空",
            warning="HoYoLAB 签到已启用但 Cookie 为空，未执行签到",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    act_id = str(config.get("actId") or DEFAULT_ACT_ID).strip()
    timeout = int(config.get("timeoutSec") or DEFAULT_TIMEOUT_SEC)
    retry_count = max(1, int(config.get("retryCount") or DEFAULT_RETRY_COUNT))

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
            warning=f"查询 HoYoLAB 签到状态失败: {info_err or '未知错误'}",
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
    if retcode != 0:
        msg = info_resp.get("message") or f"未知错误码 {retcode}"
        result.update(
            status="warning",
            message=f"接口异常: {msg}",
            warning=f"HoYoLAB 签到状态接口异常: {msg}",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    info_data = info_resp.get("data") or {}
    is_signed = bool(info_data.get("is_sign", False))
    total_days = int(info_data.get("total_sign_day") or 0)
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

    # 2. Perform check-in
    sign_resp: dict[str, Any] | None = None
    sign_err: str | None = None
    for attempt in range(retry_count):
        sign_resp, sign_err = submit_checkin(cookie_str, act_id=act_id, timeout=timeout)
        if sign_resp is not None or attempt == retry_count - 1:
            break
        time.sleep(1)

    if sign_err or not sign_resp:
        result.update(
            status="warning",
            message="提交签到失败",
            warning=f"提交 HoYoLAB 签到失败: {sign_err or '未知错误'}",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    sign_retcode = sign_resp.get("retcode")
    if sign_retcode == 0:
        new_total = total_days + 1
        award = fetch_award_name(act_id=act_id, day_index=new_total, timeout=timeout)
        result.update(
            status="success",
            signedToday=True,
            totalSignDays=new_total,
            reward=award,
            message=f"签到成功！累计 {new_total} 天" + (f" ({award})" if award else ""),
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    if sign_retcode == -5003:
        result.update(
            status="already_signed",
            signedToday=True,
            message=f"今日已签到过 (累计 {total_days} 天)",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    if sign_retcode == 1034:
        result.update(
            status="warning",
            message="触发人机验证",
            warning="HoYoLAB 签到触发人机验证码 (1034)，请在网页或手机客户端完成一次签到以解除风控",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    if sign_retcode == -100:
        result.update(
            status="warning",
            message="Cookie 已失效",
            warning="HoYoLAB Cookie 已失效或未登录 (-100)，请更新 config/hoyolab.json",
            elapsedSec=round(time.time() - started_at, 3),
        )
        return result

    sign_msg = sign_resp.get("message") or f"错误码 {sign_retcode}"
    result.update(
        status="warning",
        message=f"签到异常: {sign_msg}",
        warning=f"HoYoLAB 签到提交失败: {sign_msg}",
        elapsedSec=round(time.time() - started_at, 3),
    )
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
