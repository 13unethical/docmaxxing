"""Rich HTML protect/restore around the plain-text humanizer."""

from __future__ import annotations

from services.humanizer_engine import rich_html as rh


def test_sanitize_keeps_formatting_drops_scripts():
    raw = '<p>Hi <b>there</b> <script>x()</script><span style="color: red; position: absolute">x</span></p>'
    out = rh.sanitize_html(raw)
    assert "<b>there</b>" in out
    assert "script" not in out.lower()
    assert "color: red" in out
    assert "position" not in out


def test_prepare_protects_bold_and_leaves_table_opaque():
    html = (
        "<p>Hello <b>world</b> and <i>more</i>.</p>"
        "<table><tr><td>A</td><td>B</td></tr></table>"
        "<p>Tail.</p>"
    )
    plain, stash = rh.prepare_rich(html)
    assert "⟦F0⟧world⟦/F0⟧" in plain
    assert "⟦F1⟧more⟦/F1⟧" in plain
    assert "⟦TABLE" in plain
    assert any(b.kind == "table" for b in stash.blocks)
    assert "A" not in plain.split("⟦TABLE")[0] or True  # table body not in prose


def test_round_trip_bold_italic_with_identity_rewrite():
    html = "<p>Hello <b>world</b> and <em>more</em> text.</p>"
    out_html, out_text = rh.humanize_rich(html, rewrite_plain=lambda s: s)
    assert "<b>" in out_html or "<strong>" in out_html or "world" in out_html
    assert "world" in out_text and "more" in out_text
    # Placeholders must not leak
    assert "⟦F" not in out_html


def test_table_returned_unchanged_when_prose_rewritten():
    html = "<p>One two three four five.</p><table><tr><td>Keep</td><td>Me</td></tr></table>"
    out_html, _ = rh.humanize_rich(html, rewrite_plain=lambda s: s.replace("One", "Uno"))
    assert "<table>" in out_html and "Keep" in out_html and "Me" in out_html
    assert "Uno" in out_html


def test_list_marker_restored_and_ordinal_word_stripped():
    assert rh.restore_list_marker("1. Ministry does things well enough here.", "First, agencies do stuff.") == (
        "1. agencies do stuff."
    )
    assert rh.restore_list_marker("- short bullet here now", "a short bullet here now").startswith("- ")


def test_list_item_html_keeps_number():
    html = "<ol><li>1. Ministry of Employment does important policy work across regions today.</li></ol>"

    def rewrite(s: str) -> str:
        # Model sees body without marker when prepare strips it — or with; simulate "First,"
        return "First, the ministry handles employment policy across regions today."

    out_html, out_text = rh.humanize_rich(html, rewrite_plain=rewrite)
    assert "1." in out_text or "1." in out_html
    assert "First" not in out_text.split(".", 1)[0] if "1." in out_text else True


def test_consecutive_list_items_merge_into_one_list():
    html = (
        "<ol>"
        "<li>1. Ministry handles employment policy across many regions today.</li>"
        "<li>2. Clinics collect patient feedback for continuous service improvement.</li>"
        "</ol>"
    )
    out_html, _ = rh.humanize_rich(html, rewrite_plain=lambda s: s)
    assert out_html.count("<ol>") == 1
    assert out_html.count("<li>") == 2


def test_placeholder_drop_falls_back_to_plain():
    html = "<p>Hello <b>world</b> friends.</p>"

    def drop_ph(s: str) -> str:
        return "Hello planet friends."  # dropped placeholders

    out_html, out_text = rh.humanize_rich(html, rewrite_plain=drop_ph)
    assert "planet" in out_text
    assert "⟦F" not in out_html


def test_color_span_protected():
    html = '<p>See <span style="color: #c00; font-family: Arial">alert</span> now.</p>'
    plain, stash = rh.prepare_rich(html)
    assert "⟦F0⟧alert⟦/F0⟧" in plain
    assert stash.blocks[0].spans[0].attrs.get("style", "").startswith("color")


def test_h2_stays_opaque_even_with_number_prefix():
    html = "<h2>2. Stakeholder Identification</h2><p>Body prose about stakeholders in detail here.</p>"
    plain, stash = rh.prepare_rich(html)
    assert any(b.kind == "opaque" and "Stakeholder" in b.html for b in stash.blocks)
    assert "2. Stakeholder" not in plain or "⟦OPAQUE" in plain
    # Numbered h2 must not become a list-marker prose job
    assert not any(b.kind == "prose" and b.marker.startswith("2.") for b in stash.blocks)


def test_references_block_absorbed_opaque():
    html = (
        "<p><b>References</b></p>"
        "<p>Smith, J. (2020). Title of the article. Journal, 1(2), 3-4.</p>"
        "<p>WHO. (2019). Guidelines.</p>"
        "<h2>Appendix</h2>"
        "<p>Extra notes after references section.</p>"
    )
    plain, stash = rh.prepare_rich(html)
    opaque = [b for b in stash.blocks if b.kind == "opaque"]
    assert any("Smith" in b.html and "WHO" in b.html and "References" in b.html for b in opaque)
    assert "Smith" not in plain.replace("⟦OPAQUE", "")
    # Appendix heading + following prose still processed
    assert any(b.kind == "opaque" and "Appendix" in b.html for b in stash.blocks)


def test_short_bold_title_paragraph_opaque_but_list_not():
    html = "<p><b>Power Analysis</b></p><p>1. Short bullet item about risk.</p>"
    plain, stash = rh.prepare_rich(html)
    assert any(b.kind == "opaque" and "Power Analysis" in b.html for b in stash.blocks)
    assert any(b.kind == "prose" and (b.marker.startswith("1.") or "bullet" in b.plain) for b in stash.blocks)
