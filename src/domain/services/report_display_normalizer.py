"""Presentation-only normalization for generated group-report text."""
from __future__ import annotations

from ..models.data_models import (
    GoldenQuote,
    QualityReview,
    SummaryTopic,
    UserTitle,
)


class ReportDisplayNormalizer:
    """Applies administrator-configured literal display replacements.

    It intentionally operates on generated report fields, never on raw chat
    history, account IDs, or user display names. It is presentation cleanup,
    not a moderation bypass mechanism.
    """

    def __init__(self, replacements: dict[str, str] | None = None):
        pairs = replacements or {}
        # Longest first avoids a short key changing part of a longer key first.
        self._pairs = sorted(
            (
                (str(source), str(target))
                for source, target in pairs.items()
                if str(source)
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )

    def text(self, value: str) -> str:
        value = str(value or "")
        for source, target in self._pairs:
            value = value.replace(source, target)
        return value

    def topics(self, items: list[SummaryTopic]) -> list[SummaryTopic]:
        for item in items:
            item.topic = self.text(item.topic)
            item.detail = self.text(item.detail)
        return items

    def user_titles(self, items: list[UserTitle]) -> list[UserTitle]:
        for item in items:
            item.title = self.text(item.title)
            item.reason = self.text(item.reason)
        return items

    def golden_quotes(self, items: list[GoldenQuote]) -> list[GoldenQuote]:
        for item in items:
            item.content = self.text(item.content)
            item.reason = self.text(item.reason)
        return items

    def quality_review(self, item: QualityReview | None) -> QualityReview | None:
        if not item:
            return None
        item.title = self.text(item.title)
        item.subtitle = self.text(item.subtitle)
        item.summary = self.text(item.summary)
        for dimension in item.dimensions:
            dimension.name = self.text(dimension.name)
            dimension.comment = self.text(dimension.comment)
        return item
