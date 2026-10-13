"""Local HoYoLAB credentials, protected for the current Windows user only."""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import uuid

MAX_COOKIE_LENGTH = 32768


class CredentialError(ValueError):
    """An intentionally non-sensitive credential error."""


def validate_cookie(cookie: str) -> str:
    if not isinstance(cookie, str) or not cookie.strip() or len(cookie) > MAX_COOKIE_LENGTH or '\r' in cookie or '\n' in cookie:
        raise CredentialError('Cookie 格式无效，请在本机重新配置')
    return cookie.strip()


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != 'nt':
        raise CredentialError('本机凭据需要 Windows 当前用户 DPAPI')
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = _Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    function.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN only: deliberately no LOCAL_MACHINE flag.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise CredentialError('本机凭据保护或解密失败，请由当前 Windows 用户重新配置')
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def protect_cookie(cookie: str) -> str:
    try:
        return base64.b64encode(_crypt(validate_cookie(cookie).encode('utf-8'), decrypt=False)).decode('ascii')
    except CredentialError:
        raise
    except Exception:
        raise CredentialError('本机凭据保护失败') from None


def unprotect_cookie(blob: str) -> str:
    try:
        if not isinstance(blob, str) or not blob or len(blob) > 100000:
            raise ValueError()
        return validate_cookie(_crypt(base64.b64decode(blob, validate=True), decrypt=True).decode('utf-8'))
    except Exception:
        raise CredentialError('本机凭据解密失败，请由当前 Windows 用户重新配置') from None


def load_cookie(config: dict) -> str:
    if 'cookieDpapi' in config:
        return unprotect_cookie(config['cookieDpapi'])
    cookie = config.get('cookie', '')
    if isinstance(cookie, dict):
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in cookie.items()):
            raise CredentialError('Cookie 格式无效，请在本机重新配置')
        if any('\r' in part or '\n' in part for pair in cookie.items() for part in pair):
            raise CredentialError('Cookie 格式无效，请在本机重新配置')
        cookie = '; '.join(f'{k.strip()}={v.strip()}' for k, v in cookie.items())
    return validate_cookie(cookie)


def save_cookie_config(config_path: Path, cookie: str) -> None:
    """Atomically save ciphertext; no plaintext files or backups are created."""
    ciphertext = protect_cookie(cookie)
    path = Path(config_path)
    temporary = None
    try:
        config = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
        if not isinstance(config, dict):
            raise ValueError()
        config.pop('cookie', None)
        config.update(enabled=True, cookieDpapi=ciphertext)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.hoyolab-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        raise CredentialError('本机凭据配置保存失败') from None
    finally:
        if temporary is not None and temporary.exists():
            # Preserve failed encrypted writes in a private recovery directory.
            # Never permanently delete a file while recovering a failed save.
            try:
                recovery = path.parent / '.hoyolab-credential-quarantine'
                recovery.mkdir(exist_ok=True)
                os.replace(temporary, recovery / (uuid.uuid4().hex + '.tmp'))
            except OSError:
                pass  # The ignored encrypted temporary file remains recoverable.
