from __future__ import annotations

from edgefinance.media import episode_id_for, frame_durations, podcast_schema, prepare_podcast_packet, srt_time, validate_podcast_script


def test_episode_id_and_srt_time():
    assert episode_id_for("2026-09-20") == "2026-w38"
    assert srt_time(65.432) == "00:01:05,432"
    timeline = [{"start_seconds": 1.5}, {"start_seconds": 4.0}, {"start_seconds": 8.0}]
    durations = frame_durations(timeline, 10.0)
    assert durations == [4.0, 4.0, 2.0]
    assert sum(durations) == 10.0


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
    sentence = "我們先確認這項公開資料的比較口徑，再討論它對技術成熟與公司價值取得可能代表什麼，同時保留反方解釋與下一步查證條件。這裡還要區分來源陳述、我們的推論與尚待取得的估值資料，避免把研究順位誤寫成預期報酬。"
    turns = []
    for index in range(1, 35):
        text = sentence
        if index in {1, 2}:
            text = "歡迎收聽 edgeFinance4Podcast。" + sentence
        if index in set(range(3, 11)):
            text = "這項判斷目前最需要追問的是什麼？我們能用哪個條件驗證？"
        turns.append({"turn": index, "speaker": "host" if index % 2 else "cohost", "text": text,
            "delivery": "clear", "source_ids": [f"e{(index % 5) + 1}"]})
    script = {
        "schema_version": 1, "id": "2026-w38", "status": "draft", "publish_date": "2026-09-20",
        "show_name": "edgeFinance4Podcast", "title": "專利與風險的本週交叉訊號", "subtitle": "從公開證據辨認機會、限制與失效條件",
        "summary": "Ying 與 Bing 逐步比較本週技術、公司與景氣證據，保留來源限制並提出下一週可驗證的問題。",
        "language": "zh-Hant", "estimated_minutes": 14,
        "hosts": [{"id": "host", "display_name": "Ying", "role": "證據主持人"}, {"id": "cohost", "display_name": "Bing", "role": "風險主持人"}],
        "source_report_id": "2026-09-20-abcdef12", "source_ids": [f"e{i}" for i in range(1, 6)],
        "learning_goals": ["理解專利邊界", "辨認價值取得", "追蹤市場風險"],
        "chapters": [{"title": f"章節 {i}", "summary": "整理證據、反方解釋與下一步查證。", "turn_start": start, "accent": "orange"}
            for i, start in enumerate([1, 9, 17, 25], 1)],
        "dialogue": turns,
        "fact_checks": [{"claim": f"核心主張 {i}", "source_ids": [f"e{i}"], "boundary": "只代表來源目前所述範圍。"} for i in range(1, 6)],
        "closing_takeaways": ["先核對來源", "再比較替代解釋", "最後追蹤失效條件"],
        "disclosure": "本集使用本機合成 Ying 與 Bing 語音，內容是公開證據研究討論，不是個人化投資建議。",
        "youtube": {"title": "專利、公司與風險｜edgeFinance4Podcast", "description": "本集根據已發布週報，討論技術成熟、價值取得與市場風險。書面週報：https://example.com/report.html\n" + "\n".join(f"來源：https://example.com/{i}" for i in range(1, 6)) + "\n本集使用合成語音，內容是研究討論而非投資建議。",
            "thumbnail_headline": "專利與風險交叉訊號", "tags": ["投資研究", "專利", "科技", "總體經濟", "Podcast"],
            "pinned_comment": "你認為哪一項失效條件最值得追蹤？歡迎提出反方資料與可驗證問題，書面週報、完整來源及研究邊界請見說明欄。"},
    }
    validate_podcast_script(script, packet)
    assert podcast_schema("2026-w38", packet["report_id"], packet["show"]["name"])["additionalProperties"] is False
