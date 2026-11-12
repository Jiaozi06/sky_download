"""Read the current public APK URL from HONOR App Market on an ADB device."""

import argparse
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep
from xml.etree import ElementTree

from update_downloads import OUTPUT


MARKET = "com.hihonor.appmarket"
PACKAGE = "com.netease.sky.honor"
DUMP = "/sdcard/sky-honor-window.xml"
RECORD = re.compile(
    rf"mPkgName='{re.escape(PACKAGE)}', mVersionCode=(\d+),"
    r"[^\r\n]*?mTotalSize=(\d+),[^\r\n]*?mDownloadUrl='"
    r"(https://apppkg-[a-z0-9-]+-drcn\.hihonorcdn\.com/apk/upload_\d+\.apk)'"
)


def adb(*args):
    return subprocess.check_output(("adb", *args), timeout=25).decode("utf-8", "replace")


def open_details():
    adb("shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
        "-d", f"honormarket://details?id={PACKAGE}", "-p", MARKET)


def tap(node):
    bounds = re.findall(r"\d+", node.get("bounds", ""))
    if len(bounds) != 4:
        return False
    x0, y0, x1, y1 = map(int, bounds)
    adb("shell", "input", "tap", str((x0 + x1) // 2), str((y0 + y1) // 2))
    return True


def handle_startup(nodes):
    labels = {node.get("text", "") for node in nodes}
    if any("responding" in label for label in labels):
        launcher = any("Launcher" in label for label in labels)
        action = "android:id/aerr_close" if launcher else "android:id/aerr_wait"
        for node in nodes:
            if node.get("resource-id") == action:
                return tap(node)
    welcome = "欢迎使用" in labels or "应用市场隐私声明" in labels
    if welcome:
        for node in nodes:
            if node.get("package") == MARKET and node.get("checkable") == "true" and node.get("checked") == "false":
                return tap(node)
        for label in ("下一页", "同意", "同意并继续", "同意并使用", "开始使用"):
            for node in nodes:
                if node.get("text") == label and node.get("package") == MARKET:
                    return tap(node)
    for node in nodes:
        if node.get("resource-id") in {
            "com.android.permissioncontroller:id/permission_allow_button",
            "com.android.permissioncontroller:id/permission_allow_foreground_only_button",
        }:
            return tap(node)
    return False


def details(existing_log):
    if not existing_log:
        open_details()
    deadline = monotonic() + 120
    reopen_at = monotonic() + 10
    nodes = []
    while monotonic() < deadline:
        adb("shell", "rm", "-f", DUMP)
        try:
            adb("shell", "uiautomator", "dump", DUMP)
            nodes = list(ElementTree.fromstring(
                adb("exec-out", "cat", DUMP)
            ).iter("node"))
        except subprocess.CalledProcessError as error:
            if error.returncode != 139:
                raise
            sleep(1)
            continue
        except ElementTree.ParseError:
            # Android may return no hierarchy while the first activity is starting.
            sleep(1)
            continue
        by_id = {node.get("resource-id"): node for node in nodes}
        if any(node.get("text") == "本地区暂未提供服务" for node in nodes):
            raise ValueError("荣耀应用市场的设备地区不受支持，请检查模拟器国家设置")
        version = next((by_id[f"{MARKET}:id/{name}"] for name in
                        ("tv_version_name", "zy_tv_version_name", "tv_version")
                        if f"{MARKET}:id/{name}" in by_id), None)
        button = next((by_id[f"{MARKET}:id/{name}"] for name in
                       ("app_detail_download_btn", "app_detail_download_btn_small", "market_download_btn")
                       if f"{MARKET}:id/{name}" in by_id), None)
        if button is not None and button.get("enabled") == "true":
            match = re.search(r"\d+(?:\.\d+)+", version.get("text", "")) if version is not None else None
            bounds = re.findall(r"\d+", button.get("bounds", ""))
            if len(bounds) == 4:
                x0, y0, x1, y1 = map(int, bounds)
                if x1 > x0 and y1 > y0:
                    return match[0] if match else "", str((x0 + x1) // 2), str((y0 + y1) // 2)
        if not existing_log:
            if handle_startup(nodes):
                reopen_at = monotonic() + 5
            elif monotonic() >= reopen_at:
                open_details()
                reopen_at = monotonic() + 10
        sleep(1)
    labels = [node.get("text") for node in nodes if node.get("text")]
    ids = [node.get("resource-id") for node in nodes if node.get("resource-id")]
    raise ValueError("荣耀应用市场没有打开可下载的光·遇详情页。当前界面：" + " / ".join(labels[:8])
                     + "；控件：" + " / ".join(ids[:40] + ids[-15:]))


def capture(existing_log):
    version, x, y = details(existing_log)
    log_process = None
    live_log = None
    if not existing_log:
        start = int(adb("shell", "date", "+%s").strip())
        debug = Path(os.environ.get("RUNNER_TEMP", ".")) / "honor-detail"
        with tempfile.NamedTemporaryFile(prefix="honor-download-", suffix=".log", delete=False) as output:
            live_log = Path(output.name)
        with live_log.open("wb") as output:
            log_process = subprocess.Popen(("adb", "logcat", "-v", "epoch", "-T", "1", "-s", "AMLog[8d4e9cb8fb]:I"),
                                           stdout=output, stderr=subprocess.DEVNULL)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            debug.with_suffix(".xml").write_text(adb("exec-out", "cat", DUMP), encoding="utf-8")
            debug.with_suffix(".png").write_bytes(subprocess.check_output(
                ("adb", "exec-out", "screencap", "-p"), timeout=25))
        print(f"点击荣耀下载坐标 {x},{y}")
        adb("shell", "input", "tap", x, y)
        sleep(1)
        adb("shell", "uiautomator", "dump", DUMP)
        try:
            nodes = list(ElementTree.fromstring(adb("exec-out", "cat", DUMP)).iter("node"))
            handle_startup(nodes)
            labels = [node.get("text") or node.get("content-desc") for node in nodes
                      if node.get("text") or node.get("content-desc")]
            print("点击下载后的界面：" + " / ".join(labels[:18]))
        except ElementTree.ParseError:
            pass
    try:
        deadline = monotonic() + 25
        diagnostics = []
        while monotonic() < deadline:
            lines = (live_log.read_text(encoding="utf-8", errors="replace") if live_log else
                     adb("logcat", "-d", "-v", "epoch", "-s", "AMLog[8d4e9cb8fb]:I")).splitlines()
            for line in reversed(lines):
                if not existing_log and (not line[:1].isdigit() or float(line.split()[0]) < start):
                    continue
                if PACKAGE in line:
                    diagnostics.append(line[-1200:])
                match = RECORD.search(line)
                if match:
                    code, size, url = match.groups()
                    release = {"url": url, "size": int(size), "version_code": int(code), "verified": True}
                    if version:
                        release["version"] = version
                    return release
            if existing_log:
                break
            sleep(0.3)
    finally:
        if log_process is not None:
            log_process.terminate()
            log_process.wait(timeout=8)
        if not existing_log:
            if os.environ.get("GITHUB_ACTIONS") == "true":
                debug.with_suffix(".log").write_bytes(live_log.read_bytes())
                debug.with_name("honor-detail-after.png").write_bytes(subprocess.check_output(
                    ("adb", "exec-out", "screencap", "-p"), timeout=25))
            adb("shell", "am", "force-stop", MARKET)
            live_log.unlink(missing_ok=True)
    for line in dict.fromkeys(diagnostics[-10:]):
        print(line)
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
    print(f"荣耀 {release.get('version', '')} ({release['version_code']}) {release['url']}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, ElementTree.ParseError, subprocess.SubprocessError) as error:
        message = " ".join(str(error).splitlines())
        print(f"::error::{message}" if os.environ.get("GITHUB_ACTIONS") == "true" else message)
        raise SystemExit(1)
