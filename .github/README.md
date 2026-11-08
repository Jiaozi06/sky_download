# 光·遇下载链接

[downloads.json](../downloads.json) 保存网易官服、哔哩哔哩、vivo、应用宝、4399、233 乐园、华为和荣耀的安卓下载地址。华为附带的 HMS Core 位于 `channels.huawei.dependencies.hms_core`。

GitHub Actions 每 10 分钟分别检查网易官服和华为 AppGallery 海外版的版本及构建号。网易更新时统一刷新国服渠道和 HMS Core。国际服更新时只刷新 `international`。两边的检查互不依赖，只有 JSON 发生变化才提交。渠道发包时间可能不同，记录中的版本来自各自渠道。GitHub 的定时任务可能延迟，公开仓库连续 60 天无活动时，GitHub 会停用定时任务。

- 网易使用固定下载入口，打开时会生成当前 APK 的临时地址。
- `verified: true` 表示下载探测读取了 APK 文件头并核对了可用的大小信息。探测只读取文件头。
- `verified: false` 表示本次探测失败，`error` 提供原因。若渠道没有返回地址且有历史记录，则保留旧链接并标记 `stale: true`。
- 4399 下载需要使用 JSON 里的 `headers.User-Agent`。其余渠道有直链时可直接请求 `url`。
- 国际服位于 `international`，包含 Google Play 商店入口及华为 AppGallery 海外版 APK。新 APK 通过检查后才替换旧链接。
- 荣耀位于 `channels.honor`。网易构建变更时，Action 会在临时 Android 模拟器里尝试获取荣耀 CDN 地址。首次启动停在荣耀的隐私声明时，会保留上次验证的链接，并继续发布其他渠道的更新。已打开光·遇详情页且暂停测试下载的本地模拟器，可通过 `python scripts/update_honor.py --existing-log` 读取记录并刷新 JSON。

本地运行（Python 3.10 或更高版本）：

```sh
python scripts/update_downloads.py
python scripts/sky_channel_links.py huawei hms_core international_huawei --json
```

## 部署到 Vercel

在 Vercel 导入本仓库，Framework Preset 选择 **Other**，Root Directory 设为 **`web`**，启用 **Include source files outside of the Root Directory in the Build Step**。关闭 **Skip deployment for unaffected projects**，让根目录的 JSON 提交也触发部署。构建命令和输出目录由 `web/vercel.json` 提供。

- 打开网站首页可查看各渠道的下载按钮。
- 给首页请求加上 `type: json` 请求头，可获得原始 JSON。也可以直接请求 `/downloads.json`。
- 浏览器无法添加专用下载请求头或渠道直链未通过验证时，按钮会打开官方渠道页。

```sh
curl -H "type: json" https://your-project.vercel.app/
```
