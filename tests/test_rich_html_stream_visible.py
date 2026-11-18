"""Stream callbacks must never expose ⟦OPAQUE⟧ / ⟦TABLE⟧ protect markers."""

from __future__ import annotations

from services.humanizer_engine.rich_html import humanize_rich


def test_stream_emits_heading_text_not_opaque_token():
    html = (
        "<h1>Artificial Intelligence: Its Impact on Modern Society</h1>"
        "<p>The study examines how remote work changed productivity across 42 firms in 2021. "
        "Researchers found that output rose by 13 percent while meetings declined sharply.</p>"
    )
    events: list[dict] = []

    def rewrite(line: str) -> str:
        return line.replace("study", "paper").replace("examines", "explores").replace(
            "changed", "shifted"
        ).replace("found", "showed").replace("rose", "grew").replace(
            "while", "whereas"
        ).replace("declined", "fell").replace("Researchers", "Authors")

    rich, text = humanize_rich(html, rewrite, max_workers=1, on_chunk=events.append)
    assert "OPAQUE" not in rich
    assert "OPAQUE" not in text
    streamed = "\n".join(e["text"] for e in events)
    assert "⟦OPAQUE" not in streamed
    assert "Artificial Intelligence" in streamed
    assert any(e["status"] == "ready" for e in events)
