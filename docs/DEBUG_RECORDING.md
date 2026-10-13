# 轻量实机调试录屏

复用现有 `scripts/run_daily_recorded.ps1` 和本机FFmpeg/NVENC录屏路径。单项天赋只读调试可运行：

```powershell
./scripts/run_daily_recorded.ps1 -Profile cultivation -CultivationMode scan -CultivationTalentPreview -TalentType elemental-skill -DebugRecording -TimeoutMinutes 8
```

`-DebugRecording` 使用960像素宽（1920×1080窗口对应960×540）、8帧/秒、CQ32、平均400kbps/上限500kbps，无音频；十分钟视频约30～40MB，实际大小以文件为准。此规格只用于回看导航和操作，不能替代原始1920×1080截图、时间、数量、费用及前后核验。正式既有录屏档的帧率/覆盖契约保持。

调试录屏等待当前实际原生进程和本批配置的启动通过记录后才开始；启动及登录界面不录制。它绑定该次原神窗口，写入同批私有logs/runs目录，结束后沿用ffprobe时长/帧数核验与结果关联。调试期间需要重新登录时，先停止录屏再由用户操作凭据。

仅保存本机，不发布视频、截图、日志或凭据；旧视频不自动删除。`-CheckOnly` 可在不启动游戏和录屏的情况下核实FFmpeg路径与编码规格。新增开关只改变调试视频规格及开始时机，不授权升级、刷怪、领奖或其他消费。

一次单项只读实机验证已生成52.375秒、419帧的960×540视频，实际8帧/秒、文件约1.2MB，ffprobe帧覆盖率为1。启动检查的日志目录参数已修正并增加真实目录读取回归。录屏从原生启动通过后开始，单项流程未升级或消费；视频结束与游戏窗口退出相关的采集终止信息会保留在本机记录，不能据视频完整就宣称游戏任务成功。
