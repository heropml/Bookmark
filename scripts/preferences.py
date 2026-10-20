"""Private homepage preferences, atomic writes and reversible local snapshots."""
from __future__ import annotations

import json
import re
import threading
import time
import uuid

import settings

LOCK = threading.RLock()
MAX_BYTES = 512 * 1024
BACKUP_LIMIT = 20
# Ordinary saves keep at most one snapshot per interval: the state before a burst of edits.
BACKUP_INTERVAL = 300
CHOICES = {
    "skin": "auto aurora cyber ember abyss nebula prism obsidian paper snow sakura celadon shuimo daiqing zhusha yemo",
    "icon": "logo letter glass neon gem holo mono pixel outline halo frame badge ink grain mirror circuit",
    "layout": "classic compact list icons board tree tabs start accordion waterfall shelves index table tiles split text",
    "motion": "float pulse sweep sway bounce spin ripple flip shake zoom slide twist blink drift heartbeat still",
    "trail": "stardust comet bubble petal firefly rainbow sparkle sparks ribbon notes pixels crystal ink hearts smoke none",
    "sky": "auto rain snow stars meteor fireflies blossom aurora bubbles fireworks matrix nebula ripples beams confetti none",
    "fx": "on off",
    "focus": "on off",
}
KEYS = {"bm-" + key for key in CHOICES} | {
    "bm-pins", "bm-card-density", "bm-trail-size", "bm-sky-size", "bm-sky-count",
    "bm-appearance-presets", "bm-category-layout", "bm-city",
}
# Earlier builds also stored the current category. It now stays in each browser, so switching
# categories in one tab neither conflicts with other tabs nor rotates out real backups.
LEGACY_KEYS = {"bm-folder"}
LABELS = {"bm-pins": "置顶", "bm-appearance-presets": "外观方案",
          "bm-category-layout": "分类布局", "bm-city": "城市"}


class Conflict(ValueError):
    """Another page changed the same field after this page read it."""


def validate(values):
    """Validate the complete string-valued storage snapshot before replacing any data."""
    if not isinstance(values, dict):
        raise ValueError("配置包含未知字段")
    values = {key: value for key, value in values.items() if key not in LEGACY_KEYS}
    if not values.keys() <= KEYS:
        raise ValueError("配置包含未知字段")
    if len(json.dumps(values, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
        raise ValueError("配置文件过大")
    for key, value in values.items():
        if not isinstance(value, str):
            raise ValueError("配置值必须是文本")
        field = key[3:]
        if field in CHOICES and value not in CHOICES[field].split():
            raise ValueError("外观选项无效")
        if field in ("card-density", "trail-size", "sky-size", "sky-count"):
            number = float(value)
            if field == "card-density":
                valid = number in (60, 70, 80, 90, 100, 110, 120)
            else:
                low, step = (0.25, 0.25) if field == "sky-count" else (0.5, 0.1)
                valid = low <= number <= 2.5 and abs(number / step - round(number / step)) < 0.00001
            if not valid:
                raise ValueError("外观数值超出范围")
        if field == "pins":
            pins = json.loads(value)
            if not isinstance(pins, list) or len(pins) > 2000 or any(
                not isinstance(url, str) or not url or len(url) > 8192 for url in pins
            ) or len(set(pins)) != len(pins):
                raise ValueError("置顶列表无效")
        if field == "appearance-presets":
            presets = json.loads(value)
            if not isinstance(presets, list):
                raise ValueError("外观方案无效")
            # The appearance UI deliberately retains incompatible presets from newer versions.
            # Keep those opaque entries intact rather than losing them during migration.
        if field == "category-layout":
            layout = json.loads(value)
            if not isinstance(layout, dict) or any(
                not isinstance(item, dict)
                or ("order" in item and (not isinstance(item["order"], list)
                                        or any(not isinstance(name, str) for name in item["order"])))
                or ("width" in item and item["width"] not in ("small", "medium", "large"))
                for item in layout.values()
            ):
                raise ValueError("分类顺序无效")
        if field == "city":
            city = json.loads(value)
            if not isinstance(city, dict) or not isinstance(city.get("name"), str):
                raise ValueError("城市配置无效")
    return values


def read_document(path):
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES + 4096:
        raise ValueError("配置文件过大")
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("format") != 1:
        raise ValueError("配置文件格式无效")
    document["values"] = validate(document.get("values"))
    if not isinstance(document.get("revision"), str) or not re.fullmatch(r"[a-f0-9]{32}", document["revision"]):
        raise ValueError("配置版本无效")
    return document


def load():
    with LOCK:
        try:
            document = read_document(settings.DATA_DIR / "preferences.json")
        except FileNotFoundError:
            return {"exists": False, "revision": None, "values": {}}
        return {"exists": True, **document}


def backup_files():
    folder = settings.DATA_DIR / ".preferences-backups"
    return sorted((p for p in folder.glob("*.json") if re.fullmatch(r"[a-f0-9]{32}", p.stem)),
                  key=lambda p: p.stat().st_mtime_ns, reverse=True)


def backups():
    with LOCK:
        result = []
        for path in backup_files():
            item = {"id": path.stem, "created": path.stat().st_mtime}
            try:
                item["pins"] = len(json.loads(read_document(path)["values"].get("bm-pins", "[]")))
            except (OSError, ValueError, TypeError):
                item["error"] = "备份无法读取"
            result.append(item)
        return result


def snapshot_due():
    try:
        newest = backup_files()[:1]
        return not newest or time.time() - newest[0].stat().st_mtime >= BACKUP_INTERVAL
    except OSError:
        # Unknown history: keeping an extra snapshot is safer than skipping one.
        return True


def write(current, values, snapshot):
    """Replace the loaded `current` document with validated `values`; call under LOCK."""
    if current["exists"] and current["values"] == values:
        return current
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if current["exists"] and (snapshot or snapshot_due()):
        folder = settings.DATA_DIR / ".preferences-backups"
        folder.mkdir(exist_ok=True)
        settings.write_atomic(folder / (uuid.uuid4().hex + ".json"),
                              (settings.DATA_DIR / "preferences.json").read_bytes())
    document = {"format": 1, "revision": uuid.uuid4().hex,
                "updated": time.time(), "values": values}
    settings.write_atomic(settings.DATA_DIR / "preferences.json",
                          json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8"))
    # Retention is housekeeping after a successful save; a locked old backup must not
    # turn a successful write into an ambiguous failure for the page.
    try:
        for path in backup_files()[BACKUP_LIMIT:]:
            try:
                path.unlink()
            except OSError:
                pass
    except OSError:
        pass
    return {"exists": True, **document}


def merge(changes, base, *, migration=False):
    """Apply only the fields a page changed. `base` holds each field as that page last knew it
    (None when absent); a field another page changed differently since then is a conflict,
    while edits to other fields from other tabs are kept."""
    if not isinstance(changes, dict) or not isinstance(base, dict) or changes.keys() != base.keys():
        raise ValueError("配置修改无效")
    if any(value is not None and not isinstance(value, str) for value in (*changes.values(), *base.values())):
        raise ValueError("配置值必须是文本")
    changes = {key: value for key, value in changes.items() if key not in LEGACY_KEYS}
    if not changes.keys() <= KEYS:
        raise ValueError("配置包含未知字段")
    rejected = []
    if migration:
        if any(base[key] is not None for key in changes):
            raise ValueError("首次迁移不能包含已有配置的原值")
        accepted = {}
        for key, value in changes.items():
            try:
                validate({key: value})
            except (ValueError, TypeError):
                rejected.append(key)
            else:
                accepted[key] = value
        changes = accepted
    with LOCK:
        current = load()
        if migration and not changes:
            return {**current, "rejected": rejected}
        values = dict(current["values"])
        conflicts = [key for key, value in changes.items() if values.get(key) not in (base[key], value)]
        if conflicts:
            names = "、".join(dict.fromkeys(LABELS.get(key, "外观") for key in sorted(conflicts)))
            raise Conflict(f"其他页面已修改{names}，请刷新后再修改；本次未覆盖本地配置。")
        for key, value in changes.items():
            if value is None:
                values.pop(key, None)
            else:
                values[key] = value
        result = write(current, validate(values), snapshot=False)
        return {**result, "rejected": rejected} if migration else result


def replace(values):
    """Replace everything (import); the current configuration is always backed up first."""
    values = validate(values)
    with LOCK:
        return write(load(), values, snapshot=True)


def restore(snapshot_id):
    if not isinstance(snapshot_id, str) or not re.fullmatch(r"[a-f0-9]{32}", snapshot_id):
        raise ValueError("备份编号无效")
    with LOCK:
        snapshot = read_document(settings.DATA_DIR / ".preferences-backups" / (snapshot_id + ".json"))
        return replace(snapshot["values"])
