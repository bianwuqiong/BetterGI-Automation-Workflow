"""Read-only Windows game identity for the runner; no input, launch or resize."""
import os
from pathlib import Path
try:from .named_inventory_capture import rectangle_core
except ImportError:from named_inventory_capture import rectangle_core


def query_game_context(pid,expected_executable):
    if type(pid) is not int or pid<=0 or not isinstance(expected_executable,(str,Path)):
        raise ValueError('named inventory requires runner-selected game identity')
    if os.name!='nt':raise ValueError('named inventory game identity query requires Windows')
    import ctypes
    from ctypes import wintypes
    user=ctypes.WinDLL('user32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True);dwm=ctypes.WinDLL('dwmapi',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    user.SetThreadDpiAwarenessContext.argtypes=[wintypes.HANDLE];user.SetThreadDpiAwarenessContext.restype=wintypes.HANDLE
    user.GetForegroundWindow.restype=wintypes.HWND
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes=[wintypes.HWND];user.IsIconic.argtypes=[wintypes.HWND]
    user.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM);user.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
    dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:raise ValueError('named inventory actual game process unavailable')
    try:
        length=wintypes.DWORD(32768);buffer=ctypes.create_unicode_buffer(length.value)
        if not kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(length)):raise ValueError('named inventory actual executable unavailable')
        actual=Path(buffer.value).resolve(strict=True);expected=Path(expected_executable).resolve(strict=True)
        if os.path.normcase(str(actual))!=os.path.normcase(str(expected)):raise ValueError('named inventory actual game executable mismatch')
        creation,exit_time,kernel_time,user_time=(wintypes.FILETIME() for i in range(4))
        if not kernel.GetProcessTimes(handle,*(ctypes.byref(v) for v in (creation,exit_time,kernel_time,user_time))):
            raise ValueError('named inventory actual process start unavailable')
        ticks=((creation.dwHighDateTime<<32)|creation.dwLowDateTime)+504911232000000000
    finally:kernel.CloseHandle(handle)
    windows=[]
    def inspect(hwnd,unused):
        owner=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid and user.IsWindowVisible(hwnd) and not user.IsIconic(hwnd):windows.append(int(hwnd))
        return True
    if not user.EnumWindows(callback_type(inspect),0) or len(windows)!=1:raise ValueError('named inventory requires one visible non-minimized game window')
    hwnd=windows[0]
    if int(user.GetForegroundWindow() or 0)!=hwnd:raise ValueError('named inventory actual game is not foreground')
    previous=user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    if not previous:raise ValueError('named inventory physical pixel query context unavailable')
    try:
        client=wintypes.RECT();outer=wintypes.RECT()
        if not user.GetClientRect(hwnd,ctypes.byref(client)) or dwm.DwmGetWindowAttribute(hwnd,9,ctypes.byref(outer),ctypes.sizeof(outer))!=0:
            raise ValueError('named inventory actual physical capture geometry unavailable')
        width,height=client.right-client.left,client.bottom-client.top
        if (width,height)!=(1920,1080):raise ValueError('named inventory physical game client must be 1920x1080')
        rectangle={'x':outer.left,'y':outer.bottom-height,'width':width,'height':height}
    finally:
        if not user.SetThreadDpiAwarenessContext(previous):raise ValueError('named inventory physical query context restoration failed')
    owner=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
    if owner.value!=pid or int(user.GetForegroundWindow() or 0)!=hwnd:raise ValueError('named inventory actual game binding changed during query')
    return {'source':'runner_windows_os_preflight','processId':pid,'windowHandle':hwnd,'processStartedUtcTicks':str(ticks),
        'executablePath':str(actual),'captureRectangle':rectangle,'foregroundWindowHandle':hwnd}


def validate_game_context(context,binding):
    """Only controller-generated context belongs here, never a request/raw copy."""
    if not isinstance(context,dict) or context.get('source')!='runner_windows_os_preflight' or not isinstance(binding,dict):
        raise ValueError('named inventory independent runner game context missing')
    for key in ('processId','windowHandle','processStartedUtcTicks'):
        if binding.get(key)!=context.get(key):raise ValueError('named inventory PID/window/start/physical geometry changed')
    if rectangle_core(binding.get('captureRectangle'),require_derived=True)!=rectangle_core(context.get('captureRectangle'),allow_derived=False):
        raise ValueError('named inventory physical capture geometry changed')
    if context.get('foregroundWindowHandle')!=context.get('windowHandle'):raise ValueError('named inventory runner foreground game identity unverified')
    if not isinstance(context.get('executablePath'),str) or not isinstance(binding.get('executablePath'),str) or os.path.normcase(context['executablePath'])!=os.path.normcase(binding['executablePath']):
        raise ValueError('named inventory independent executable identity mismatch')
