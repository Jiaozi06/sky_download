"""Refresh mainland and international download links on independent version changes."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

from sky_channel_links import CHANNELS, OFFICIAL_URL, international_huawei, official, resolve


OUTPUT = Path(__file__).resolve().parents[1] / "downloads.json"
GOOGLE_PLAY_URL = "https://play.google.com/store/apps/details?id=com.tgc.sky.android"
MAINLAND_CHANNELS = [name for name in CHANNELS if name not in {"official", "international_huawei"}]


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


def refresh_mainland(previous):
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
    with ThreadPoolExecutor(max_workers=len(MAINLAND_CHANNELS) + 1) as pool:
        official_probe = pool.submit(resolve, "official", current)
        for result in pool.map(resolve, MAINLAND_CHANNELS):
            channel = result["channel"]
            old = previous_channels.get(channel, {})
            if channel == "hms_core":
                old = previous_channels.get("huawei", {}).get("dependencies", {}).get(channel, {})
            results[channel] = record(result, old)
        official_record = record(official_probe.result(), {})
    # The signed CDN URL expires even if the build has not changed.
    official_record.update(url=OFFICIAL_URL, link_type="download_page")
    results["huawei"]["dependencies"] = {"hms_core": results.pop("hms_core")}
    print(f"网易官服更新到 {current.version} ({current.version_code})")
    return {
        "official_version": current.version,
        "official_version_code": current.version_code,
        "channels": {"official": official_record, **results},
    }


def refresh_international(previous):
    international = previous.get("international", {})
    old = international.get("huawei", {})
    current = international_huawei()
    old_code = old.get("version_code", 0)
    if current.version_code < old_code:
        print(f"忽略国际服返回的较早构建 {current.version_code}，当前已发布 {old_code}")
        return
    if (current.version, current.version_code) == (old.get("version"), old_code) and old.get("verified"):
        print(f"国际服 {current.version} 未更新")
        return

    result = resolve("international_huawei", current)
    if not result["verified"]:
        raise ValueError(f"新 APK 验证失败，将在下次检查重试：{result['error']}")
    print(f"国际服更新到 {current.version}")
    return {"international": {"google_play": GOOGLE_PLAY_URL, **international, "huawei": record(result, old)}}


def update(output=OUTPUT):
    previous = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    changes = {}
    failed = False
    with ThreadPoolExecutor(max_workers=2) as pool:
        checks = {
            "国服": pool.submit(refresh_mainland, previous),
            "国际服": pool.submit(refresh_international, previous),
        }
        for name, check in checks.items():
            try:
                changes.update(check.result() or {})
            except (URLError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                print(f"{name}检查失败：{error}")
                failed = True

    if changes:
        document = {"schema_version": 1, **previous, **changes}
        document["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        pending = output.with_suffix(".json.tmp")
        pending.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pending.replace(output)
        print(f"已更新 {output.name}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(update())
