from __future__ import annotations

from edgefinance.media import episode_id_for, frame_durations, podcast_schema, prepare_podcast_packet, public_podcast_source, srt_time, validate_podcast_script, wrap_pixels


def test_episode_id_and_srt_time():
    assert episode_id_for("2026-09-20") == "2026-w38"
    assert srt_time(65.432) == "00:01:05,432"
    timeline = [{"start_seconds": 1.5}, {"start_seconds": 4.0}, {"start_seconds": 8.0}]
    durations = frame_durations(timeline, 10.0)
    assert durations == [4.0, 4.0, 2.0]
    assert sum(durations) == 10.0
    source = public_podcast_source({"id": "e1", "url": "https://example.com", "published_at": "2026-09-20",
        "source_id": "taiwan-revenue", "title": "TSM · 2026-08 月營收", "statement": "不應公開"})
    assert source["title"] == "TSM · 2026-08 · monthly revenue"
    assert "statement" not in source


def test_english_video_wrap_keeps_words_intact():
    from PIL import Image, ImageDraw, ImageFont
    draw = ImageDraw.Draw(Image.new("RGB", (320, 200)))
    text = "We connect durable optical links with Taiwan revenue observations."
    lines = wrap_pixels(draw, text, ImageFont.load_default(size=18), 155)
    assert " ".join(lines).split() == text.split()
    assert any("Taiwan" in line for line in lines)


def test_packet_is_bounded_and_traceable(project):
    report = {
        "id": "2026-09-20-abcdef12", "as_of": "2026-09-20", "summary": "本週摘要", "status": "partial",
        "coverage": {}, "theses": [{"evidence_ids": ["e1"], "counterevidence_ids": ["e2"]}],
        "risks": [{"evidence_ids": ["e3"]}], "next_week": [], "weekly_comparisons": [], "risk_history": [],
        "patent_landscape": {}, "opportunities": {}, "sources": [], "limitations": [],
        "evidence": [
            {"id": f"e{i}", "title": f"來源 {i}", "url": f"https://example.com/{i}", "published_at": "2026-09-20",
             "source_id": "test", "statement": f"可核對主張 {i}", "caution": "仍待覆核", "type": "source_statement"}
            for i in range(1, 31)
        ],
    }
    packet = prepare_podcast_packet(project, report)
    assert packet["episode_id"] == "2026-w38"
    assert [item["id"] for item in packet["sources"][:3]] == ["e1", "e2", "e3"]
    assert len(packet["sources"]) == 24
    assert packet["written_report_url"].endswith("report-2026-09-20-abcdef12.html")


def test_validates_balanced_source_bounded_dialogue():
    packet = {
        "episode_id": "2026-w38", "report_id": "2026-09-20-abcdef12",
        "show": {"name": "edgeFinance4Podcast"}, "written_report_url": "https://example.com/report.html",
        "sources": [{"id": f"e{i}", "title": f"來源 {i}", "url": f"https://example.com/{i}"} for i in range(1, 6)],
    }
    sentence = ("We first verify the comparison used by the public source, then discuss what it may imply for technology maturity and corporate value capture. "
        "We also separate the source statement from our inference, preserve a credible counterargument, identify missing valuation evidence, and define the next condition that could disprove the thesis.")
    turns = []
    for index in range(1, 35):
        text = sentence
        if index in {1, 2}:
            text = "Welcome to edgeFinance4Podcast. " + sentence
        if index in set(range(3, 11)):
            text = "What should we challenge here, and which observable condition could test it?"
        turns.append({"turn": index, "speaker": "host" if index % 2 else "cohost", "text": text,
            "delivery": "clear", "source_ids": [f"e{(index % 5) + 1}"]})
    script = {
        "schema_version": 1, "id": "2026-w38", "status": "draft", "publish_date": "2026-09-20",
        "show_name": "edgeFinance4Podcast", "title": "This Week's Patent and Risk Cross-Signals", "subtitle": "Using public evidence to separate opportunity, uncertainty, and invalidation",
        "summary": "Ying and Bing compare this week's technology, company, and macroeconomic evidence while preserving source limits and defining questions that can be tested next week.",
        "language": "en-US", "estimated_minutes": 14,
        "hosts": [{"id": "host", "display_name": "Ying", "role": "Evidence host"}, {"id": "cohost", "display_name": "Bing", "role": "Risk host"}],
        "source_report_id": "2026-09-20-abcdef12", "source_ids": [f"e{i}" for i in range(1, 6)],
        "learning_goals": ["Understand patent boundaries", "Identify value capture", "Track market risk"],
        "chapters": [{"title": f"Chapter {i}", "summary": "Organize the evidence, counterargument, and next verification step.", "turn_start": start, "accent": "orange"}
            for i, start in enumerate([1, 9, 17, 25], 1)],
        "dialogue": turns,
        "fact_checks": [{"claim": f"Core claim {i}", "source_ids": [f"e{i}"], "boundary": "This is limited to what the cited source currently reports."} for i in range(1, 6)],
        "closing_takeaways": ["Verify the source first", "Compare alternative explanations", "Track the invalidation condition"],
        "disclosure": "This episode uses locally generated synthetic speech for Ying and Bing. It is an evidence-led research discussion, not individualized investment advice.",
        "youtube": {"title": "Patents, Companies, and Risk | edgeFinance4Podcast", "description": "This episode uses the published weekly report to discuss technology maturity, value capture, and market risk. Read the full written report at https://example.com/report.html.\n" + "\n".join(f"Original source: https://example.com/{i}" for i in range(1, 6)) + "\nYing and Bing use synthetic speech. This is evidence-led research, not individualized investment advice.",
            "thumbnail_headline": "Patent and Risk Cross-Signals", "tags": ["investment research", "patents", "technology", "macroeconomics", "podcast"],
            "pinned_comment": "Which invalidation condition should we track first? Share a traceable counter-source or testable question, and use the written report links for the full evidence boundary."},
    }
    validate_podcast_script(script, packet)
    assert podcast_schema("2026-w38", packet["report_id"], packet["show"]["name"])["additionalProperties"] is False
