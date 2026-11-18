"""Streaming chunk callbacks for the student humanizer."""

from __future__ import annotations

from services.humanizer_engine.student_humanizer import StudentConfig, StudentTextHumanizer


def test_humanize_emits_chunks_as_completed():
    text = (
        "The study examines how remote work changed productivity across 42 firms in 2021. "
        "Researchers found that output rose by 13 percent while meetings declined sharply (Smith, 2020).\n\n"
        "The study examines how remote work changed productivity across 42 firms in 2021. "
        "Researchers found that output rose by 13 percent while meetings declined sharply (Smith, 2020)."
    )
    events: list[dict] = []
    swaps = {
        "study": "paper",
        "examines": "explores",
        "changed": "shifted",
        "found": "showed",
        "rose": "grew",
        "while": "whereas",
        "declined": "fell",
        "sharply": "steeply",
        "Researchers": "Authors",
        "how": "the way",
        "across": "in",
        "output": "production",
    }

    def rewrite(chunk: str) -> str:
        return " ".join(swaps.get(w, w) for w in chunk.split())

    engine = StudentTextHumanizer(
        StudentConfig(
            url="https://student.test",
            api_key="k",
            model="m",
            share=1.0,
            level=8,
            timeout=30.0,
            chunk_words=1,
            pick="changed",
            sampling=((1.0, 1),),
        ),
        complete_fn=rewrite,
    )
    out = engine.humanize(text, on_chunk=events.append)
    assert out.strip()
    ready = [e for e in events if e["status"] == "ready"]
    assert len(ready) >= 2
    assert ready[0]["rewrite_done"] == 1
    assert all("index" in e and "text" in e for e in ready)
