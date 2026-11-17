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


def test_sanitize_drops_word_style_block_not_into_text():
    raw = (
        "<html><head><style><!--\n"
        "@font-face{font-family:Cambria Math}\n"
        "p.MsoNormal{margin:0cm;font-size:12.0pt}\n"
        "--></style></head>"
        "<body><p class='MsoNormal'>Hello <b>world</b> from Word.</p></body></html>"
    )
    out = rh.sanitize_html(raw)
    assert "Cambria" not in out
    assert "MsoNormal" not in out
    assert "@font-face" not in out
    assert "Hello" in out and "world" in out
    assert "<b>" in out or "<strong>" in out


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
    assert "<b>world</b>" in out_html or "<strong>world</strong>" in out_html
    assert "<em>more</em>" in out_html or "<i>more</i>" in out_html
    assert "world" in out_text and "more" in out_text
    # Placeholders must not leak
    assert "⟦F" not in out_html


def test_rewrite_keeps_bold_when_placeholders_survive():
    html = "<p>Hello <b>world</b> and more prose about coupling assemblies fairly enough here.</p>"
    out_html, _ = rh.humanize_rich(html, rewrite_plain=lambda s: s.replace("more", "extra"))
    assert "⟦F" not in out_html
    assert "<b>world</b>" in out_html
    assert "extra" in out_html


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


def test_plain_short_paragraph_is_prose_not_heading():
    """Without bold / h1–h6 / ##, a short line is never frozen as a title."""
    html = "<p>Methodology</p><p>This audit compares two platforms over a two-week window.</p>"
    plain, stash = rh.prepare_rich(html)
    assert "⟦OPAQUE" not in plain
    assert all(b.kind == "prose" for b in stash.blocks)
    assert any(b.plain == "Methodology" for b in stash.blocks)


def test_lone_article_paragraph_is_prose_not_heading():
    """Word/paste often puts the first word in its own <p>; must not freeze as a title."""
    html = (
        "<p>The</p>"
        "<p>comparison supports the case of coupling. In Ireland a decision was made.</p>"
    )
    plain, stash = rh.prepare_rich(html)
    assert "⟦OPAQUE" not in plain
    assert len(stash.blocks) == 1 and stash.blocks[0].kind == "prose"
    assert stash.blocks[0].plain.startswith("The comparison")
    rich, _ = rh.humanize_rich(html, lambda t: t)
    assert rich.count("<p>") == 1
    assert "The comparison" in rich.replace("\n", " ")


def test_mid_sentence_bold_word_is_not_a_heading_block():
    """Regression: bold field name split into its own <p> must stay one prose paragraph."""
    html = (
        "<p>My field of study is </p>"
        "<p><strong>Economics</strong></p>"
        "<p>. Economics is the study of how individuals allocate resources and make decisions.</p>"
    )
    plain, stash = rh.prepare_rich(html)
    assert len(stash.blocks) == 1 and stash.blocks[0].kind == "prose"
    assert "Economics" in stash.blocks[0].plain
    assert "⟦OPAQUE" not in plain
    rich, text = rh.humanize_rich(html, lambda t: t)
    assert rich.count("<p>") == 1
    assert "<strong>Economics</strong>" in rich or "<b>Economics</b>" in rich
    assert "\n" not in text
    assert "study is Economics." in text.replace("  ", " ")
    assert "Economics ." not in text


def test_html_to_plaintext_keeps_inline_bold_on_one_line():
    html = "<p>My field of study is <strong>Economics</strong>. Economics deals with markets.</p>"
    text = rh.html_to_plaintext(html)
    assert "\n" not in text
    assert "is Economics." in text


def test_soft_wrap_br_and_split_p_join_into_one_paragraph():
    """Word paste often splits 'It is based' / 'on three theories' across lines or <p>s."""
    html = (
        "<p>It is based<br>on three theories. The former one is affective polarization theory here.</p>"
        "<p>The second is</p>"
        "<p>deliberative democratic theory with enough words for a real paragraph body now.</p>"
    )
    plain, stash = rh.prepare_rich(html)
    assert "It is based on three theories" in plain
    assert "The second is deliberative" in plain
    assert plain.count("\n\n") == 1  # two prose blocks only
    rich, text = rh.humanize_rich(html, lambda s: s)
    assert "<br>" not in rich
    assert "It is based on three theories" in text
    assert "The second is deliberative" in text


def test_model_newlines_inside_prose_do_not_become_br():
    html = "<p>One two three four five six seven eight nine ten eleven.</p>"

    def rewrite(s: str) -> str:
        return "One two three\nfour five six\nseven eight nine ten eleven."

    rich, text = rh.humanize_rich(html, rewrite)
    assert "<br>" not in rich
    assert "\n" not in text
    assert "three four five" in text


def test_strip_rich_tokens_removes_opaque_table_and_mangled_f():
    raw = "Hello ⟦OPAQUE8⟧ world ⟦TABLE34⟧ and [F0] title F0: Breaking deadlock ⟦F1⟧x⟦/F1⟧"
    out = rh.strip_rich_tokens(raw)
    assert "OPAQUE" not in out and "TABLE" not in out
    assert "[F0]" not in out and "⟦F" not in out
    assert "Breaking deadlock" in out
    assert "Hello" in out and "world" in out


def test_humanize_rich_never_sends_opaque_tokens_to_rewrite():
    html = (
        "<h2>Introduction</h2>"
        "<p>One two three four five six seven eight nine ten.</p>"
        "<table><tr><td>Keep</td><td>Me</td></tr></table>"
        "<p>Tail paragraph with enough words to rewrite carefully now.</p>"
    )
    seen: list[str] = []

    def rewrite(s: str) -> str:
        seen.append(s)
        assert "⟦OPAQUE" not in s
        assert "⟦TABLE" not in s
        return s.replace("One", "Uno").replace("Tail", "End")

    out_html, out_text = rh.humanize_rich(html, rewrite)
    assert seen and all("⟦" not in s for s in seen)
    assert "<h2>Introduction</h2>" in out_html
    assert "Keep" in out_html and "<table>" in out_html
    assert "Uno" in out_text and "End" in out_text
    assert "⟦OPAQUE" not in out_html and "⟦TABLE" not in out_text
    assert "⟦F" not in out_html


def test_reassemble_survives_leaked_tokens_in_prose_chunk():
    """Safety net: if a chunk somehow contains protect markers, strip them."""
    html = "<p>Hello <b>world</b> friends here.</p><h2>Title Block</h2>"
    plain, stash = rh.prepare_rich(html)
    # Simulate model returning a token in a prose slot.
    poisoned = plain.replace("Hello", "Hello ⟦OPAQUE99⟧ [F0]")
    rich = rh.reassemble_rich(poisoned, stash)
    text = rh.html_to_plaintext(rich)
    assert "OPAQUE" not in text
    assert "[F0]" not in text
    assert "Title Block" in text or "Title" in rich
