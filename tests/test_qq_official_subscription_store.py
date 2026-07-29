import asyncio

from src.infrastructure.persistence.qq_official_subscription_store import (
    QQOfficialSubscriptionStore,
)


def test_fingerprint_and_subscription_roundtrip(tmp_path):
    async def scenario():
        store = QQOfficialSubscriptionStore(tmp_path)

        assert not await store.is_certified("member-openid")
        await store.certify(
            "member-openid",
            "default_1:GroupMessage:beta-group",
            "beta-group",
        )
        assert await store.is_certified("member-openid")

        origin = "default_1:GroupMessage:target-group"
        assert not await store.is_subscribed(origin)
        await store.subscribe(origin, "default_1", "target-group", "member-openid", "23:00")
        assert await store.is_subscribed(origin)

        targets = await store.subscribed_targets()
        assert [(item[1], item[2]) for item in targets] == [("default_1", "target-group")]

        await store.mark_delivery(origin, False, "permission denied")
        await store.unsubscribe(origin, "GROUP_MSG_REJECT")
        assert not await store.is_subscribed(origin)

    asyncio.run(scenario())


def test_remove_cleans_subscription_and_active_state(tmp_path):
    async def scenario():
        store = QQOfficialSubscriptionStore(tmp_path)
        origin = "default_1:GroupMessage:g"
        await store.subscribe(origin, "default_1", "g", "u", "23:00")
        await store.mark_active_message(origin, True, "owner")

        assert await store.remove(origin, "GROUP_DEL_ROBOT") is True
        assert not await store.is_subscribed(origin)
        assert await store.remove(origin, "GROUP_DEL_ROBOT") is False

    asyncio.run(scenario())


def test_claim_due_targets_claims_once_per_day(tmp_path):
    from datetime import datetime

    async def scenario():
        store = QQOfficialSubscriptionStore(tmp_path)
        origin = "default_1:GroupMessage:g"
        await store.subscribe(origin, "default_1", "g", "u", "07:30")

        due = await store.claim_due_targets(datetime(2026, 7, 30, 7, 30), catch_up_minutes=10)
        assert [(item[1], item[2]) for item in due] == [("default_1", "g")]

        # A second check in the same day must not loop/re-run.
        due_again = await store.claim_due_targets(datetime(2026, 7, 30, 7, 31), catch_up_minutes=10)
        assert due_again == []

        # Next day can run again.
        due_tomorrow = await store.claim_due_targets(datetime(2026, 7, 31, 7, 30), catch_up_minutes=10)
        assert [(item[1], item[2]) for item in due_tomorrow] == [("default_1", "g")]

    asyncio.run(scenario())
