from services.humanizer_training import human_pairs as hp

XML = """<article><front><abstract><sec><title>Conclusions</title><p>Abstract text.</p></sec></abstract></front>
<body>
<sec><title>1. Introduction</title><p>Intro.</p></sec>
<sec><title>5. Conclusions</title>
<p>Teachers adapted quickly <xref ref-type="bibr">[12]</xref>, although support varied across schools [<xref>3</xref>, <xref>4</xref>].</p>
<p>Future work should follow the same students over time (<xref>Smith, 2019</xref>).</p>
<p>Effects are hard to capture (Ura et al., <xref>2020</xref>; Lee, <xref>2018</xref>) in schools (Corcoran et al., <xref>2018</xref>).</p>
</sec>
</body></article>"""


def test_conclusion_paragraphs_come_from_the_body_without_citations():
    assert hp.conclusion_paragraphs(XML) == [
        "Teachers adapted quickly, although support varied across schools.",
        "Future work should follow the same students over time.",
        "Effects are hard to capture in schools.",
    ]


def test_usable_conclusion_limits_length_and_prose():
    para = "Students learned more when feedback came quickly. " * 12
    assert hp.usable_conclusion([para.strip()]) == para.strip()
    assert hp.usable_conclusion(["Too short."]) is None
    assert hp.usable_conclusion([para.strip() + " See Figure 2."]) is None
    assert hp.usable_conclusion([para.strip() + " This was noted before (Ura et al. )."]) is None
    assert hp.usable_conclusion([para.strip() + " It helps (e.g.,) a lot."]) is None
    assert hp.usable_conclusion([para.strip()] * 5) is None


def test_search_keeps_only_cc_by_and_cc0():
    class Page:
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    pages = [
        {"resultList": {"result": [
            {"pmcid": "PMC1", "license": "cc by", "pubYear": "2019"},
            {"pmcid": "PMC2", "license": "cc by-nc"},
            {"pmcid": "PMC3", "license": "CC0"},
        ]}, "nextCursorMark": "a"},
        {"resultList": {"result": []}, "nextCursorMark": "a"},
    ]
    got = list(hp.search(10, get=lambda *a, **k: Page(pages.pop(0))))
    assert [r["pmcid"] for r in got] == ["PMC1", "PMC3"]
    assert got[1]["license"] == "cc0"


def test_ai_problem_and_sft_direction():
    human = "One point here. Another one.\n\nSecond paragraph stays."
    ai = "A first point is made. Another follows.\n\nThe second paragraph remains."
    assert hp.ai_problem(human, ai) is None
    assert hp.ai_problem(human, "**Conclusion**\n\n" + ai) == "MARKDOWN"
    assert hp.ai_problem(human, ai.replace("\n\n", " ")) == "PARAGRAPHS"
    ex = hp.sft_example({"ai": ai, "human": human})
    assert [m["role"] for m in ex["messages"]] == ["system", "user", "assistant"]
    assert ex["messages"][1]["content"] == ai and ex["messages"][2]["content"] == human
    assert "10/10" in ex["messages"][0]["content"]
