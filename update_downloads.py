"""Publish a new download snapshot when the NetEase Android build changes."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sky_channel_links import CHANNELS, OFFICIAL_URL, official, resolve


OUTPUT = Path(__file__).with_name("downloads.json")


def record(result, previous):
    channel = result.pop("channel")
    if not result["verified"]:
        print(f"{channel}: {result['error']}")
        if not result.get("url") and previous.get("url"):
            return {
                **{key: value for key, value in previous.items() if key != "dependencies"},
                "verified": False,
                "stale": True,
                "error": result["error"],
            }
    return result


def update(output=OUTPUT):
    previous = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    current = official()
    old_version = previous.get("official_version")
    old_code = previous.get("official_version_code", 0)
    if (current.version, current.version_code) == (old_version, old_code):
        print(f"网易官服 {current.version} ({current.version_code}) 未更新")
        return
    if current.version_code < old_code:
        print(f"忽略网易返回的较早构建 {current.version_code}，当前已发布 {old_code}")
        return

    previous_channels = previous.get("channels", {})
    results = {}
    other_channels = [channel for channel in CHANNELS if channel != "official"]
    with ThreadPoolExecutor(max_workers=len(CHANNELS)) as pool:
        official_probe = pool.submit(resolve, "official", current)
        for result in pool.map(resolve, other_channels):
            channel = result["channel"]
            old = previous_channels.get(channel, {})
            if channel == "hms_core":
                old = previous_channels.get("huawei", {}).get("dependencies", {}).get(channel, {})
            elif channel == "international_huawei":
                old = previous.get("international", {}).get("huawei", {})
            results[channel] = record(result, old)
        official_record = record(official_probe.result(), {})
    # The signed CDN URL expires even if the build has not changed.
    official_record.update(url=OFFICIAL_URL, link_type="download_page")
    results["huawei"]["dependencies"] = {"hms_core": results.pop("hms_core")}
    international_huawei = results.pop("international_huawei")

    document = {
        "schema_version": 1,
        "official_version": current.version,
        "official_version_code": current.version_code,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channels": {"official": official_record, **results},
        "international": {
            "google_play": "https://play.google.com/store/apps/details?id=com.tgc.sky.android",
            "huawei": international_huawei,
        },
    }
    pending = output.with_suffix(".json.tmp")
    pending.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(output)
    print(f"已更新 {output.name} 到网易官服 {current.version} ({current.version_code})")


if __name__ == "__main__":
    update()
