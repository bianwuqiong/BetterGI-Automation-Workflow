"""Local masked Cookie import UI; no password collection or plaintext file/log."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

try:
    from .hoyolab_credentials import save_cookie_config
except ImportError:
    from hoyolab_credentials import save_cookie_config


def main() -> None:
    root_path = Path(__file__).resolve().parent.parent
    config_path = root_path / "config" / "hoyolab.json"
    status_path = root_path / "state" / "hoyolab-credential-setup-status.json"
    window = tk.Tk()
    window.title("BetterGI — 本机 HoYoLAB Cookie 加密配置")
    window.geometry("720x340")
    window.resizable(False, False)
    window.attributes("-topmost", True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps({"saved": False, "startedAtUTC": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n", encoding="utf-8")

    tk.Label(window, text="HoYoLAB 自动签到：本机加密保存", font=("Microsoft YaHei", 15, "bold")).pack(pady=(18, 10))
    tk.Label(window, text="仅粘贴刚从官方 HoYoLAB 页面取得的 Cookie。\n不需要密码，不要将 Cookie 发到聊天中。", justify="left", font=("Microsoft YaHei", 10)).pack(pady=(0, 10))
    value = tk.StringVar()
    entry = tk.Entry(window, textvariable=value, show="●", width=78, font=("Consolas", 11))
    entry.pack(padx=24, pady=(0, 10), ipady=7)
    tk.Label(window, text="保存时使用 Windows 当前用户 DPAPI 加密；配置不保留明文。\n仅供这台电脑的当前用户运行签到脚本，不能迁移到其他机器。", justify="left", font=("Microsoft YaHei", 9), fg="#555555").pack(pady=(0, 10))
    state = tk.StringVar(value="等待粘贴 Cookie 并保存。")
    tk.Label(window, textvariable=state, wraplength=660, font=("Microsoft YaHei", 10)).pack(pady=(4, 6))

    def save() -> None:
        cookie = value.get()
        try:
            save_cookie_config(config_path, cookie)
        except Exception:
            # Input/error representations may contain authentication material.
            state.set("未保存。请确认输入是非空、完整的一行 Cookie 值，没有换行或整段请求。")
            return
        value.set("")
        entry.delete(0, tk.END)
        try:
            if window.clipboard_get().strip() == cookie:
                window.clipboard_clear()
                window.update()
        except tk.TclError:
            pass
        cookie = ""
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps({
            "saved": True,
            "protection": "Windows-DPAPI-CurrentUser",
            "configPath": "config/hoyolab.json",
            "savedAtUTC": datetime.now(timezone.utc).isoformat(),
            "plaintextStored": False,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        state.set("已加密保存。随后由助手验证实际签到状态；此处不会提交签到。")
        button.configure(state=tk.DISABLED)
        window.after(1500, window.destroy)

    button = tk.Button(window, text="加密保存到本机", command=save, font=("Microsoft YaHei", 11), width=22)
    button.pack(pady=(2, 12))
    entry.focus_set()
    window.mainloop()


if __name__ == "__main__":
    main()
