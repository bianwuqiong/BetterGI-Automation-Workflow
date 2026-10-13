# 本机原神国际服登录凭据录入

此工具只提供本人手工录入、明确覆盖和不含秘密的状态查询。源码按本仓库 GPL v3 发布；密码、账号值、编译产物、授权收据和本机状态均不随源码发布。

在项目根目录运行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_genshin_login_credentials.ps1`，工具会构建到私有 `state/genshin-login-credential-ui/bin/Release/net8.0-windows` 并打开可见窗口。账号和密码仅在窗口输入；不要发给代理，不接受命令行或环境变量凭据。已有凭据只能由本人点击明确覆盖按钮替换。保存和自动重登复选框由本人操作，复选框默认未勾选。

可用 `-Mode Status` 查询是否存在凭据及是否允许自动重登，只返回成功、存在、允许状态和固定凭据引用。`-Mode SelfTest` 运行合成数据测试，不读取真实 Windows 凭据，也不启动游戏。构建保留已有加密收据，不要求重复录入。

固定引用为 `BetterGI-Automation-Workflow/GenshinImpact/International/Main`。Windows 凭据管理器中的内容额外使用当前用户 DPAPI 加密，私有授权收据通过 HMAC 绑定当前 Windows SID、引用、`loginOnly`、勾选状态和本次录入 ID。凭据与收据不匹配时禁止自动输入。当前 Windows 用户下的其他程序仍可能访问其凭据；此设计不声称能隔离恶意同用户程序。

工具没有密码取出接口、任意输入接口、切换账号或游戏消费权限。实际登录由 BetterGI 内部固定操作完成，须核验官方游戏进程、当前窗口、登录表单及密码框焦点。验证码、OTP、新设备验证和其他未知页面交给本人处理。填写和提交不能当作成功；成功需真实进入大世界并留下不含凭据的验收记录。

WinForms 会持有输入控件的托管字符串；工具在保存后清空控件，自己持有的字节、字符和原生缓冲在退出路径清零，不对系统内部副本或不可变字符串作完全清零保证。只在本机明确授权后启用自动重登。
