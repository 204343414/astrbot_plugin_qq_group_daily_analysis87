import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from astrbot.api import AstrBotConfig
from src.infrastructure.config.config_manager import ConfigManager
from src.infrastructure.reporting.generators import ReportGenerator
from src.domain.models.data_models import (
    GroupStatistics,
    SummaryTopic,
    UserTitle,
    GoldenQuote,
    QualityReview,
    QualityDimension,
    ActivityVisualization,
    EmojiStatistics,
    TokenUsage,
)

@pytest.mark.anyio
async def test_mock_analysis_image_generation_with_diagnostics():
    cfg = AstrBotConfig({})
    cm = ConfigManager(cfg)
    rg = ReportGenerator(cm, Path("/tmp"))

    stats = GroupStatistics(
        message_count=128,
        total_characters=4580,
        participant_count=12,
        most_active_period="20:00-21:00",
        golden_quotes=[
            GoldenQuote(content="测试金句", sender="测试群友", reason="幽默", user_id="mock_user_1")
        ],
        emoji_count=18,
        emoji_statistics=EmojiStatistics(face_count=10, other_emoji_count=8),
        activity_visualization=ActivityVisualization(
            hourly_activity={"12:00": 10, "20:00": 25},
            daily_activity={"2026-09-15": 128},
        ),
        token_usage=TokenUsage(),
        chat_quality_review=QualityReview(
            title="质量锐评",
            subtitle="测试",
            dimensions=[
                QualityDimension(name="技术探讨", percentage=50.0, comment="优秀", color="#4CAF50")
            ],
            summary="讨论热烈",
        ),
    )

    analysis_result = {
        "statistics": stats,
        "topics": [
            SummaryTopic(
                topic="T2I 排障",
                contributors=["测试群友"],
                detail="测试报告生成",
                contributor_ids=["mock_user_1"],
            )
        ],
        "user_titles": [
            UserTitle(
                name="测试群友",
                user_id="mock_user_1",
                title="排障官",
                mbti="INTJ",
                reason="协助测试",
            )
        ],
        "user_analysis": {},
        "chat_quality_review": stats.chat_quality_review,
    }

    mock_render = AsyncMock(return_value=b"\xff\xd8\xff\xe0mock_image_data")
    diag = {}

    url, html = await rg.generate_image_report(
        analysis_result=analysis_result,
        group_id="mock_group_123",
        html_render_func=mock_render,
        template_override="ATRI",
        diagnostics=diag,
    )

    assert url is not None
    assert html is not None
    assert diag.get("final_status") == "SUCCESS"
    assert diag.get("template_name") == "ATRI"
    assert diag.get("jinja_ms") > 0
    assert len(diag.get("attempts", [])) == 1
    assert diag["attempts"][0]["status"] == "SUCCESS"
