"""Persistent beta fingerprints and QQ Official daily-analysis subscriptions."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class QQOfficialSubscriptionStore:
    """Small atomic JSON store for QQ Official specialization.

    The data intentionally lives outside AstrBot config: subscriptions are
    runtime state created by group owners/managers, while config remains the
    operator-edited policy surface.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "qq_official_daily_subscriptions.json"
        self._lock = asyncio.Lock()
        self._data = self._load()

    @staticmethod
    def _initial() -> dict[str, Any]:
        return {
            "schema_version": 1,
            "fingerprints": {},
            "subscriptions": {},
            "active_message": {},
        }

    def _load(self) -> dict[str, Any]:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            data = self._initial()
            self._write_atomic(data)
            return data
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if not isinstance(loaded, dict):
            loaded = {}
        data = self._initial()
        data.update(loaded)
        for key in ("fingerprints", "subscriptions", "active_message"):
            if not isinstance(data.get(key), dict):
                data[key] = {}
        return data

    def _write_atomic(self, value: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix="qq_official_daily_subscriptions.",
            suffix=".tmp",
            dir=self.data_dir,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(value, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp_name, self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    async def certify(self, member_openid: str, origin: str, group_openid: str) -> None:
        member_openid = str(member_openid or "").strip()
        if not member_openid:
            raise ValueError("member_openid is required")
        now = int(time.time())
        async with self._lock:
            self._data["fingerprints"][member_openid] = {
                "origin": str(origin or ""),
                "group_openid": str(group_openid or ""),
                "certified_at": now,
                "last_seen_at": now,
            }
            self._write_atomic(self._data)

    async def is_certified(self, member_openid: str) -> bool:
        member_openid = str(member_openid or "").strip()
        if not member_openid:
            return False
        async with self._lock:
            item = self._data["fingerprints"].get(member_openid)
            if isinstance(item, dict):
                item["last_seen_at"] = int(time.time())
                self._write_atomic(self._data)
                return True
            return False

    async def subscribe(
        self,
        origin: str,
        platform_id: str,
        group_openid: str,
        member_openid: str,
    ) -> None:
        origin = str(origin or "").strip()
        if not origin:
            raise ValueError("origin is required")
        now = int(time.time())
        async with self._lock:
            prior = self._data["subscriptions"].get(origin)
            if not isinstance(prior, dict):
                prior = {}
            prior.update(
                {
                    "subscribed": True,
                    "platform_id": str(platform_id or ""),
                    "group_openid": str(group_openid or ""),
                    "subscribed_by": str(member_openid or ""),
                    "subscribed_at": prior.get("subscribed_at") or now,
                    "last_probe_at": now,
                    "last_seen_at": now,
                    "last_delivery": "NEVER",
                    "last_error": "",
                }
            )
            prior.pop("unsubscribed_reason", None)
            prior.pop("unsubscribed_at", None)
            self._data["subscriptions"][origin] = prior
            self._write_atomic(self._data)

    async def unsubscribe(self, origin: str, reason: str = "manual") -> bool:
        origin = str(origin or "").strip()
        if not origin:
            return False
        async with self._lock:
            item = self._data["subscriptions"].get(origin)
            if not isinstance(item, dict) or not bool(item.get("subscribed", False)):
                return False
            item["subscribed"] = False
            item["unsubscribed_reason"] = str(reason or "manual")
            item["unsubscribed_at"] = int(time.time())
            self._write_atomic(self._data)
            return True

    async def remove(self, origin: str, reason: str = "removed") -> bool:
        origin = str(origin or "").strip()
        if not origin:
            return False
        async with self._lock:
            existed = self._data["subscriptions"].pop(origin, None) is not None
            self._data["active_message"].pop(origin, None)
            if existed:
                self._write_atomic(self._data)
            return existed

    async def mark_delivery(self, origin: str, success: bool, error: str = "") -> None:
        origin = str(origin or "").strip()
        if not origin:
            return
        async with self._lock:
            item = self._data["subscriptions"].get(origin)
            if not isinstance(item, dict):
                return
            item["last_delivery"] = "SUCCESS" if success else "FAILED"
            item["last_delivery_at"] = int(time.time())
            item["last_error"] = str(error or "")[:500]
            self._write_atomic(self._data)

    async def mark_active_message(self, origin: str, enabled: bool, operator_openid: str = "") -> None:
        origin = str(origin or "").strip()
        if not origin:
            return
        async with self._lock:
            self._data["active_message"][origin] = {
                "enabled": bool(enabled),
                "op_member_openid": str(operator_openid or ""),
                "updated_at": int(time.time()),
            }
            self._write_atomic(self._data)

    async def is_subscribed(self, origin: str) -> bool:
        origin = str(origin or "").strip()
        async with self._lock:
            item = self._data["subscriptions"].get(origin)
            return bool(isinstance(item, dict) and item.get("subscribed", False))

    async def subscribed_targets(self) -> list[tuple[str, str, str, dict[str, Any]]]:
        async with self._lock:
            result = []
            for origin, item in self._data["subscriptions"].items():
                if not isinstance(item, dict) or not bool(item.get("subscribed", False)):
                    continue
                platform_id = str(item.get("platform_id") or "")
                group_openid = str(item.get("group_openid") or "")
                if not platform_id or not group_openid:
                    parts = str(origin).split(":", 2)
                    if len(parts) == 3:
                        platform_id = platform_id or parts[0]
                        group_openid = group_openid or parts[2]
                if platform_id and group_openid:
                    result.append((str(origin), platform_id, group_openid, dict(item)))
            return result
