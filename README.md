# 光·遇下载链接

[downloads.json](downloads.json) 保存网易官服、哔哩哔哩、vivo、应用宝、4399、233 乐园和华为的安卓下载地址。华为附带的 HMS Core 位于 `channels.huawei.dependencies.hms_core`。

GitHub Actions 每小时第 04、14、24、34、44、54 分钟（UTC）检查网易安卓下载页。只有网易的版本或构建号发生变化，才查询其他渠道并提交 JSON。首次生成也会查询全部渠道。渠道发包时间可能不同，记录中的版本来自各自渠道。GitHub 的定时任务可能延迟，公开仓库连续 60 天无活动时，GitHub 会停用定时任务。

- 网易使用固定下载入口，打开时会生成当前 APK 的临时地址。
- `verified: true` 表示下载探测读取了 APK 文件头并核对了可用的大小信息。探测只读取文件头。
- `verified: false` 表示本次探测失败，`error` 提供原因。若渠道没有返回地址且有历史记录，则保留旧链接并标记 `stale: true`。
- 4399 下载需要使用 JSON 里的 `headers.User-Agent`。其余渠道有直链时可直接请求 `url`。
- 国际服位于 `international`，包含 Google Play 商店入口及华为 AppGallery 海外版 APK。国际服和 HMS Core 也随网易官服变更时查询。

本地运行（Python 3.10 或更高版本）：

```sh
python update_downloads.py
python sky_channel_links.py huawei hms_core international_huawei --json
```
