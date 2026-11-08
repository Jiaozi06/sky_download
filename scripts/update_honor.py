"""Read the current public APK URL from HONOR App Market on an ADB device."""

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep
from xml.etree import ElementTree

from update_downloads import OUTPUT


MARKET = "com.hihonor.appmarket"
PACKAGE = "com.netease.sky.honor"
DUMP = "/sdcard/sky-honor-window.xml"
RECORD = re.compile(
    rf"mPkgName='{re.escape(PACKAGE)}', mVersionCode=(\d+), mFlag='downloadButton'"
    r"[^\r\n]*?mTotalSize=(\d+),[^\r\n]*?mDownloadUrl='"
    r"(https://apppkg-[a-z0-9-]+-drcn\.hihonorcdn\.com/apk/upload_\d+\.apk)'"
)


def adb(*args):
    return subprocess.check_output(("adb", *args), timeout=25).decode("utf-8", "replace")


def details(existing_log):
    if not existing_log:
        adb("shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
            "-d", f"honormarket://details?id={PACKAGE}", "-p", MARKET)
    deadline = monotonic() + 40
    while monotonic() < deadline:
        adb("shell", "rm", "-f", DUMP)
        try:
            adb("shell", "uiautomator", "dump", DUMP)
        except subprocess.CalledProcessError as error:
            if error.returncode != 139:
                raise
        nodes = {node.get("resource-id"): node for node in ElementTree.fromstring(
            adb("exec-out", "cat", DUMP)
        ).iter("node")}
        version = nodes.get(f"{MARKET}:id/tv_version_name")
        button = nodes.get(f"{MARKET}:id/app_detail_download_btn")
        if version is not None and button is not None:
            match = re.search(r"\d+(?:\.\d+)+", version.get("text", ""))
            bounds = re.findall(r"\d+", button.get("bounds", ""))
            if match and len(bounds) == 4:
                x0, y0, x1, y1 = map(int, bounds)
                return match[0], str((x0 + x1) // 2), str((y0 + y1) // 2)
        sleep(1)
    raise ValueError("荣耀应用市场没有打开可下载的光·遇详情页")


def capture(existing_log):
    version, x, y = details(existing_log)
    if not existing_log:
        start = int(adb("shell", "date", "+%s").strip())
        adb("shell", "input", "tap", x, y)
    try:
        deadline = monotonic() + 25
        while monotonic() < deadline:
            lines = adb("logcat", "-d", "-v", "epoch", "-s", "AMLog[8d4e9cb8fb]:I").splitlines()
            for line in reversed(lines):
                if not existing_log and (not line[:1].isdigit() or float(line.split()[0]) < start):
                    continue
                match = RECORD.search(line)
                if match:
                    code, size, url = match.groups()
                    return {"url": url, "size": int(size), "version": version,
                            "version_code": int(code), "verified": True}
            if existing_log:
                break
            sleep(0.3)
    finally:
        if not existing_log:
            adb("shell", "am", "force-stop", MARKET)
    raise ValueError("荣耀日志没有返回当前渠道包的 CDN 地址")


def verify(release):
    curl = "curl.exe" if os.name == "nt" else "curl"
    data = subprocess.check_output((
        curl, "-q", "-fsS", "--max-time", "20", "--range", "0-3", "--max-filesize", "4",
        "--include", release["url"],
    ), timeout=25)
    headers, separator, payload = data.rpartition(b"\r\n\r\n")
    content_range = f"content-range: bytes 0-3/{release['size']}".encode()
    if not separator or payload != b"PK\x03\x04" or content_range not in headers.lower().splitlines():
        raise ValueError("荣耀 CDN 响应与应用市场 APK 记录不一致")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing-log", action="store_true", help="读取已暂停的下载记录，不开始新下载")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    document = json.loads(args.output.read_text(encoding="utf-8"))
    channels = document["channels"]
    release = capture(args.existing_log)
    old = channels.get("honor", {})
    if release["version_code"] < old.get("version_code", 0):
        raise ValueError("荣耀目录返回了比仓库更早的构建")
    verify(release)
    if release != old:
        channels["honor"] = release
        document["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        pending = args.output.with_suffix(".json.tmp")
        pending.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pending.replace(args.output)
    print(f"荣耀 {release['version']} ({release['version_code']}) {release['url']}")


if __name__ == "__main__":
    main()
