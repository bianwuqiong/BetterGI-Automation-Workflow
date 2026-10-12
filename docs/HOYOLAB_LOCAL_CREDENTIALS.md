# HoYoLAB 本机签到凭据

培养扫描不需要HoYoLAB凭据。签到使用单独的本机配置；原神资源消费授权与签到分开处理。

运行 `python scripts/setup_hoyolab_credentials.py` 打开本机遮掩输入窗口。用户在官方HoYoLAB网页自行登录、取得该会话Cookie，再粘贴到此窗口。不要将密码、验证码或Cookie发送到聊天、日志、Issue或公开仓库。

保存使用Windows当前用户范围DPAPI，配置只包含 `cookieDpapi` 密文，移除旧 `cookie` 字段。密码不参与该过程。凭据仅供本机当前用户解密，不迁移到其他机器。保存成功后清空输入；剪贴板仍为所粘贴Cookie时清空它。失败的加密临时文件保留在已忽略的恢复目录，不落明文临时文件。

本机配置及恢复文件均被Git排除：`config/hoyolab.json`、`config/.hoyolab-*.tmp` 和 `config/.hoyolab-credential-quarantine/`。旧明文配置仍兼容读取；存在密文而无法解密时拒绝签到，不能降级到旧明文。

仅检查实际状态：

```powershell
python scripts/checkin_hoyolab.py --status
```

独立执行一次签到：

```powershell
python scripts/checkin_hoyolab.py
```

这两个入口均不启动原神或BetterGI。正常日常流程会在游戏启动前调用同一签到客户端；签到缺凭据、过期、网络异常或触发验证时记录安全提示，其他流程依原有规则继续。

提交签到最多一次。成功响应、已签响应或提交结果不确定后都独立查询状态；只有结构正确且 `is_sign` 为真实布尔 `true` 才确认已签到，累计天数取回读值，不以旧值加一推算。`statusVerified` 表示状态查询已验证，`submissionAttempted` 表示本次是否提交过。返回的 `today` 取官方接口原值；签到统计时间与游戏日刷新边界分开处理。

凭据包含换行、格式错误、密文解密失败及请求异常时，错误信息不回显输入。人机验证和安全警告由用户在官方界面处理，不能绕过或自动重复提交。
