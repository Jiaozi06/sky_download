"""Print a fresh, verified APK URL for the Huawei edition of Sky (光·遇)."""

import json
import re
import sys
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


PACKAGE = "com.netease.sky.huawei"
API = "https://store-drcn.hispace.dbankcloud.com/hwmarket/api/clientApi"
SDK_USER_AGENT = "UpdateSDK##4.0.1.300##Android##Pixel 2##com.huawei.appmarket##12.0.1.301"
HUAWEI_DOMAINS = ("dbankcloud.com", "dbankcloud.cn", "dbankcdn.com", "dbankcdn.cn")
TIMEOUT = 15


def require_huawei_url(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or not any(host == domain or host.endswith("." + domain) for domain in HUAWEI_DOMAINS)
    ):
        raise ValueError("下载地址不属于华为 HTTPS CDN")


class HuaweiRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require_huawei_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_release(opener, package=PACKAGE):
    # Public update lookup for the China catalog with a generic ARM Android profile.
    form = {
        "method": "client.updateCheck",
        "ver": "1.2",
        "version": "12.0.1.301",
        "isUpdateSdk": "1",
        "serviceCountry": "CN",
        "locale": "zh_CN",
        "deviceSpecParams": json.dumps({
            "abis": "arm64-v8a,armeabi-v7a,armeabi", "dpi": 420, "preferLan": "zh"
        }),
        "pkgInfo": json.dumps({"params": [{
            "package": package, "oldVersion": "1.0", "versionCode": 1,
            "targetSdkVersion": 19, "isPre": 0, "maple": 0,
            "pkgMode": 0, "shellApkVer": 0,
        }]}),
    }
    request = Request(API, data=urlencode(form).encode(), headers={
        "User-Agent": SDK_USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with opener.open(request, timeout=TIMEOUT) as response:
        result = json.load(response)
    if result.get("rtnCode") != 0:
        raise ValueError(f"华为接口返回错误码 {result.get('rtnCode')}")
    release = next((row for row in result.get("list", []) if row.get("package") == package), None)
    if not release or not release.get("downurl"):
        raise ValueError(f"华为接口未返回 {package} 的下载地址")
    return release


def verify_apk(opener, release):
    url = release["downurl"]
    require_huawei_url(url)
    if release.get("packingType") != 0 or not urlsplit(url).path.lower().endswith(".apk"):
        raise ValueError("华为接口返回的文件不是单一 APK")
    size = int(release["fullSize"])
    if size <= 4 or int(release["size"]) != size:
        raise ValueError("华为接口返回的文件大小不是完整安装包大小")

    request = Request(url, headers={"Range": "bytes=0-3", "User-Agent": "Mozilla/5.0"})
    with opener.open(request, timeout=TIMEOUT) as response:
        if response.status == 206:
            if response.headers.get("Content-Range") != f"bytes 0-3/{size}":
                raise ValueError("华为 CDN 返回的文件大小与目录记录不符")
        elif response.status != 200 or response.headers.get("Content-Length") != str(size):
            raise ValueError("华为 CDN 未返回预期的 APK")
        if response.read(4) != b"PK\x03\x04":
            raise ValueError("华为 CDN 返回的文件头不是 APK/ZIP")
    return url, size


def main():
    opener = build_opener(HuaweiRedirects())
    try:
        release = fetch_release(opener)
        url, size = verify_apk(opener, release)
    except (URLError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"获取华为渠道包失败：{error}", file=sys.stderr)
        return 1

    print(f"{PACKAGE}  {release['version']}  {size:,} bytes", file=sys.stderr)
    digest = release.get("sha256", "")
    if re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        print(f"SHA-256（华为接口返回）：{digest}", file=sys.stderr)
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
