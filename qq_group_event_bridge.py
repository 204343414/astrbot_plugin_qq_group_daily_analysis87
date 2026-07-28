"""Runtime bridge for QQ Official group lifecycle/proactive-message events.

AstrBot v4.26.x does not forward GROUP_DEL_ROBOT / GROUP_MSG_REJECT /
GROUP_MSG_RECEIVE into the plugin event bus, while qq-botpy already parses
these events. This process-local patch does not modify AstrBot files.
"""
from __future__ import annotations

import builtins
import inspect
import logging
import weakref
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("astrbot")
_STATE_KEY = "_ASTRBOT_QQ_GROUP_LIFECYCLE_BRIDGE_V2"
Callback = Callable[[str, Any, Any], Awaitable[None]]
_EVENT_METHODS = {
    "group_del_robot": "on_group_del_robot",
    "group_msg_reject": "on_group_msg_reject",
    "group_msg_receive": "on_group_msg_receive",
}


def _state() -> dict[str, Any]:
    state = getattr(builtins, _STATE_KEY, None)
    if not isinstance(state, dict):
        state = {"installed": False, "callbacks": {}, "originals": {}}
        setattr(builtins, _STATE_KEY, state)
    return state


def install(owner: str, callback: Callback) -> None:
    state = _state()
    state["callbacks"][owner] = weakref.WeakMethod(callback)
    if state["installed"]:
        return

    from astrbot.core.platform.sources.qqofficial import qqofficial_platform_adapter as module

    originals = state.setdefault("originals", {})
    for event_name, method_name in _EVENT_METHODS.items():
        original = getattr(module.botClient, method_name, None)
        originals[method_name] = original

        async def patched(client, event, _event_name=event_name, _original=original):
            if _original is not None:
                result = _original(client, event)
                if inspect.isawaitable(result):
                    await result
            await _dispatch(_event_name, client, event)

        setattr(module.botClient, method_name, patched)

    state["installed"] = True
    logger.warning(
        "[QQGroupLifecycle] QQ Official group lifecycle runtime bridge installed: %s",
        ", ".join(sorted(_EVENT_METHODS)),
    )


def detach(owner: str) -> None:
    _state()["callbacks"].pop(owner, None)


async def _dispatch(event_name: str, client: Any, event: Any) -> None:
    state = _state()
    stale = []
    for owner, callback_ref in list(state["callbacks"].items()):
        callback = callback_ref() if callback_ref else None
        if callback is None:
            stale.append(owner)
            continue
        try:
            await callback(event_name, client, event)
        except Exception:
            logger.exception("[QQGroupLifecycle] callback failed owner=%s event=%s", owner, event_name)
    for owner in stale:
        state["callbacks"].pop(owner, None)
