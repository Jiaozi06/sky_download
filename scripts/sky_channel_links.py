"""Resolve the current Sky (光·遇) APK for each supported mainland channel."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import html
import json
import re
import sys
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener, urlopen

from huawei_sky_link import HuaweiRedirects, fetch_release, require_huawei_url


USER_AGENT = "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/133.0.0.0 Mobile Safari/537.36"
TIMEOUT = 15
OFFICIAL_URL = "https://adl.netease.com/d/g/sky/c/gw?type=android"


@dataclass
class Release:
    url: str
    version: str = ""
    size: int = 0
    fallback: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    version_code: int | None = None


def request(url, headers=None):
    return urlopen(Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})}), timeout=TIMEOUT)


def page(url, headers=None):
    with request(url, headers) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8")


def metadata(url, headers=None):
    return json.loads(page(url, headers))


def official():
    content = page(OFFICIAL_URL, {"Cache-Control": "no-cache"})
    match = re.search(r'\bandroid_link\s*=\s*android_type\s*\?\s*"(https://[^\"]+\.apk[^\"]*)"', content)
    if not match:
        raise ValueError("网易页面未提供安卓 APK")
    url = html.unescape(match[1])
    version = re.search(r"Sky-Gold-(\d+(?:\.\d+)+)-(\d+)-", urlsplit(url).path)
    if not version:
        raise ValueError("无法从网易 APK 文件名识别版本和构建号")
    return Release(url, version[1], version_code=int(version[2]))


def bilibili():
    reply = metadata(
        "https://line3-h5-pc-api.biligame.com/game/detail/game_card_info?game_base_id=101661",
        {"Referer": "https://www.biligame.com/"},
    )
    row = reply.get("data", {})
    if reply.get("code") != 0 or row.get("game_base_id") != 101661:
        raise ValueError("哔哩哔哩没有返回《光·遇》条目")
    return Release(row["android_download_link"], row["android_game_version"], int(row["android_pkg_size"]),
                   row.get("android_download_link2", ""))


def vivo():
    row = metadata(
        "https://h5-api.appstore.vivo.com.cn/detailInfo?appId=2902164&frompage=searchResultApp&h5_websource=h5appstore",
        {"Referer": "https://h5.appstore.vivo.com.cn/"},
    )
    if str(row.get("id")) != "2902164":
        raise ValueError("vivo 没有返回《光·遇》条目")
    return Release("https://appstore.vivo.com.cn/appinfo/downloadApkFile?id=2902164", row["version_name"])


def qq():
    package = "com.tencent.tmgp.eyou.eygy"
    content = page(f"https://sj.qq.com/appdetail/{package}")
    match = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', content, re.S)
    if not match:
        raise ValueError("应用宝页面没有下载数据")
    props = json.loads(match[1])["props"]["pageProps"]
    components = props["dynamicCardResponse"]["data"]["components"]
    for component in components:
        for row in (component.get("data") or {}).get("itemData") or []:
            if not isinstance(row, dict) or row.get("pkg_name") != package or not row.get("download_url"):
                continue
            source = urlsplit(row["download_url"])
            if source.hostname not in {"imtt.dd.qq.com", "imtt2.dd.qq.com"}:
                raise ValueError("应用宝返回了未知的 CDN")
            url = urlunsplit(("https", "imtt.dd.qq.com", source.path, source.query, ""))
            return Release(url, row["version_name"], int(row["apk_size"]))
    raise ValueError("应用宝没有返回《光·遇》渠道包")


def box4399():
    headers = {"User-Agent": "4399GameCenter/9.7.0.44"}
    reply = metadata("https://mapi.yxhapi.com/android/box/game/v6.5/apk.html?id=112700", headers)
    row = reply.get("result", {})
    if reply.get("code") != 100 or row.get("packag") != "com.netease.sky.m4399":
        raise ValueError("4399 没有返回《光·遇》渠道包")
    return Release(row["downurl"], size=int(row["size_byte"]), headers=headers,
                   version_code=int(row["versioncode"]))


def leyuan():
    row = metadata("https://api.233leyuan.com/game/v1/info/detail?gameId=1433471")
    if row.get("packageName") != "com.netease.sky.meta":
        raise ValueError("233 乐园没有返回《光·遇》渠道包")
    return Release(row["apkUrl64"], row["appVersionName64"], int(row["fileSize64"]),
                   version_code=int(row["appVersionCode64"]))


def huawei_package(package, *, keep_distributor=False):
    row = fetch_release(build_opener(HuaweiRedirects()), package)
    source = urlsplit(row["downurl"])
    require_huawei_url(row["downurl"])
    size = int(row["fullSize"])
    if row["packingType"] != 0 or not source.path.lower().endswith(".apk") or int(row["size"]) != size:
        raise ValueError(f"华为未提供 {package} 的完整 APK")
    query = urlencode([(key, value) for key, value in parse_qsl(source.query)
                       if keep_distributor and key == "distOpEntity"])
    direct = urlunsplit(source._replace(query=query, fragment=""))
    return Release(direct, row["version"], size, fallback=row["downurl"], version_code=int(row["versionCode"]))


CHANNELS = {
    "official": official,
    "bilibili": bilibili,
    "vivo": vivo,
    "qq": qq,
    "4399": box4399,
    "233": leyuan,
    "huawei": lambda: huawei_package("com.netease.sky.huawei"),
    "hms_core": lambda: huawei_package("com.huawei.hwid"),
    "international_huawei": lambda: huawei_package("com.tgc.sky.android.huawei", keep_distributor=True),
}


def check_apk(url, expected_size, headers):
    with request(url, {**headers, "Range": "bytes=0-3"}) as response:
        if response.status == 206:
            match = re.fullmatch(r"bytes 0-3/(\d+)", response.headers.get("Content-Range", ""))
            if not match:
                raise ValueError("CDN 返回了异常的字节范围")
            size = int(match[1])
        else:
            size = int(response.headers.get("Content-Length") or 0)
        if response.read(4) != b"PK\x03\x04" or size <= 4:
            raise ValueError("CDN 响应不是 APK")
        if expected_size and size != expected_size:
            raise ValueError(f"CDN 大小 {size} 与目录大小 {expected_size} 不一致")
        return size


def resolve(channel, release=None):
    try:
        release = release if release is not None else CHANNELS[channel]()
    except (URLError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return {"channel": channel, "verified": False, "error": str(error)}

    result = {"channel": channel, "url": release.url, "size": release.size}
    if release.version:
        result["version"] = release.version
    if release.version_code is not None:
        result["version_code"] = release.version_code
    if release.headers:
        result["headers"] = release.headers
    failures = []
    for url in filter(None, (release.url, release.fallback)):
        try:
            size = check_apk(url, release.size, release.headers)
        except (URLError, OSError, ValueError) as error:
            failures.append(str(error))
            continue
        result.update(url=url, size=size, verified=True)
        return result
    result.update(verified=False, error="; ".join(failures))
    return result


def main():
    parser = argparse.ArgumentParser(description="查询光·遇各渠道当前 APK，仅读取下载文件的前 4 字节。")
    parser.add_argument("channels", nargs="*", metavar="CHANNEL", help=", ".join(CHANNELS) + "，默认全部")
    parser.add_argument("--json", action="store_true", help="输出结构化结果，包括未验证的地址和错误")
    args = parser.parse_args()
    channels = args.channels or list(CHANNELS)
    invalid = set(channels) - CHANNELS.keys()
    if invalid:
        parser.error("未知渠道：" + ", ".join(sorted(invalid)))
    with ThreadPoolExecutor(max_workers=len(CHANNELS)) as pool:
        results = list(pool.map(resolve, dict.fromkeys(channels)))
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for result in results:
            name = result["channel"]
            if result["verified"]:
                print(result["url"] if len(results) == 1 else f"{name}\t{result['url']}")
                if result.get("headers"):
                    print(f"{name}: 下载时需要 {result['headers']}", file=sys.stderr)
            else:
                print(f"{name}: {result['error']}", file=sys.stderr)
    return 0 if all(result["verified"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
