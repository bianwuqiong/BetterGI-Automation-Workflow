# 2026-10-11 本机 BetterGI Web UI 补齐记录

本次从固定来源构建并部署了 `Assets/Map/Editor/index.html` 和 `Assets/Web/ScriptRepo/index.html`。它们是 BetterGI 上游发布流程另行构建的两个 Web 资产，不在固定引擎源码目录中，也不会由单独的 .NET 编译生成。

对应引擎基线为 `d8c0aa238a949d7d74bfe5087f3a48e39771575a`。依据该基线的 [publish.yml](https://github.com/bianwuqiong/better-genshin-impact/blob/d8c0aa238a949d7d74bfe5087f3a48e39771575a/.github/workflows/publish.yml)，分别构建以下仓库的 `build:single`，然后把 `dist/` 放入上述目录。

## 精确来源和依赖锁

| 组件 | 来源提交 | 提交时间（UTC+8） | package-lock.json SHA-256 |
|---|---|---|---|
| 地图编辑器 | [huiyadanli/bettergi-map](https://github.com/huiyadanli/bettergi-map/tree/e08ea2a47bec72783a90f507d4fa3b931ad0ff0a) / `e08ea2a47bec72783a90f507d4fa3b931ad0ff0a` | 2026-10-02 01:08:26 | `54156ce12c930e3f813284f7a29fd762e46e82bd128fcb75ad21c3dbb999390e` |
| 脚本仓库界面 | [zaodonganqi/bettergi-script-web](https://github.com/zaodonganqi/bettergi-script-web/tree/48ddacfa693d2c0c88831f44c9b2a892c1446043) / `48ddacfa693d2c0c88831f44c9b2a892c1446043` | 2026-09-22 15:01:24 | `4c2afc81b7974c1c6598ea65068120bae96b5379339de77ab35576cd0f38a26c` |

两份锁文件均为 lockfile v3；使用 `npm ci` 安装后重新核对，SHA-256 未改变。锁内 Vite 的 Node 要求为 `^20.19.0 || >=22.12.0`。本机构建使用 Node.js 22.23.3、npm 10.9.9，满足要求；地图 Vite 为 8.0.16，脚本仓库 Vite 为 8.2.1。

## 独立构建和产物

两个仓库均在独立暂存目录检出，分别执行：

```powershell
npm ci --no-audit --no-fund
npm run build:single
```

本次 npm 下载缓存位于同一暂存区域，没有全局替换 Node/npm 或系统 PATH。构建进程设为 BelowNormal，图像预处理限制为两个工作线程，以减少对只读游戏扫描的影响。

地图构建准备分层图片并生成瓦片，随后将 JS、CSS、瓦片和图标内联；脚本仓库构建生成主题 CSS 并内联 Markdown 图片。脚本仓库的 `src/styles/gen-theme-vars.css` 差异由上游生成器产生。清理生成文件时，通过构建进程内的 `preserve-build-removals.mjs` 将删除改为移入暂存区的 `quarantine-generated-build-files/`，保留恢复记录。该预加载不进入 BetterGI 运行进程，不改变 UI 业务源码。

| 部署相对路径 | 字节数 | 部署后 SHA-256 |
|---|---:|---|
| `Assets/Map/Editor/index.html` | 27,346,871 | `1001889e26734968d1a722f3bdc048e03f8b785e2df4dbb8c03e0677e706ee62` |
| `Assets/Web/ScriptRepo/index.html` | 7,401,912 | `e9a42a5954f94dac53577c011ec9ffb18a432f43c3099207e274ec0587f0d1aa` |

## 脚本仓库统计脚本的本地变更

上游 `index.html` 在 single 模式仍加载 Google Analytics。为了让本地内嵌入口不依赖这段外部统计 JS，本次只移除其加载标签和初始化代码，保留应用入口、标题及原有版权/许可证材料。主要删除段如下；完整统一差异文件还记录了文件结尾换行的归一化：

```diff
-    <!-- Google tag (gtag.js) -->
-    <script async src="https://www.googletagmanager.com/gtag/js?id=G-WXWXFJS95C"></script>
-    <script>
-      window.dataLayer = window.dataLayer || [];
-      function gtag(){dataLayer.push(arguments);}
-      gtag('js', new Date());
-
-      var config = {};
-      gtag('config', 'G-WXWXFJS95C', config);
-    </script>
```

本机保存的差异文件 `logs/setup/web-scriptrepo-local-no-analytics.patch` SHA-256 为 `55fd9d4f643540928d0e6861763bb601b43f4c1264a1bbd3d5ee41d901c0782f`。这里描述的是入口依赖；脚本仓库功能、订阅内容、在线说明或评论可能仍按上游逻辑请求网络，不能据此声称整个界面完全离线。

## 来源声明和许可证材料

两个部署目录均保留 `README.upstream.md`、`NOTICE.local-build.txt`、`THIRD_PARTY_NOTICES.json` 和实际安装依赖根目录内可用的 LICENSE、NOTICE、COPYING、COPYRIGHT 等文件；依赖清单包括构建依赖及其精确版本、下载来源和完整性标识。

- 地图源在上述提交中未提供顶层 LICENSE、LICENCE、COPYING 或 NOTICE。本次记录其来源，并保留依赖声明，没有为地图源码或图片另行指定许可证。
- 脚本仓库源的 `LICENSE` 是 GNU GPL version 3，原样保留为 `LICENSE.upstream.txt`；其 README 同时写有 Apache License 2.0。本次保留两份上游原文并记录差异，没有代替上游解决或改写这项声明。
- 本次仅作本机部署；本仓库未加入这些构建 HTML、地图图片、node_modules 或 BetterGI 二进制。

## 部署和有界验收

部署前重新确认 BetterGI 和原神进程均已停止。仅写入 `BetterGI_custom` 的两个上述 Assets 子目录，没有覆盖 User、OneDragon、工作流配置或其他资产。目标子目录原本不存在，因此没有旧内容需要隔离；部署逻辑在已有内容场景会先把整个目标子目录移入忽略的 `logs/setup/quarantine/`，再部署新文件。

本次完成的核验：

1. 两个 `build:single` 均成功退出，构建前后依赖锁哈希一致。
2. 解析两份构建 HTML，未发现外部 JS 或 CSS 启动依赖；所有非空内联脚本通过 Node 的 module 语法检查。
3. 静态核对 WebView 主机方法：`repoWebBridge` 的八个方法、`fileAccessBridge` 的三个方法，以及 `mapEditorWebBridge.ChangeMapName/RunPathing`，在固定引擎源码中均存在。这里只核对方法名称，不代表运行时行为已验收。
4. 部署文件逐一与暂存原件比对 SHA-256；地图目录 108 个文件、脚本仓库目录 303 个文件全部一致，包含上述来源和依赖声明。

**尚未打开这两个界面，尚无 WebView 实机验收。** 没有通过界面执行路线、订阅写入或游戏动作；不能把本次编译、静态核对和文件部署称为功能实测通过。

本机详细证据保存在忽略目录 `logs/setup/`：`web-ui-artifacts.json`、`web-ui-deployment.json`、`web-map-build.log`、`web-scriptrepo-build.log`、`web-scriptrepo-local-build.log` 及上述统计移除差异。独立暂存区保留源检出、原始生成文件、恢复记录和部署前产物。
