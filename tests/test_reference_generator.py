"""Reference generation reliability tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.citation_engine import generate_citation
from services.reference_generator import fetch_page_metadata


def _mock_html_response(html: str, url: str = "https://example.org/article"):
    response = MagicMock()
    response.url = url
    response.content = html.encode("utf-8")
    response.raise_for_status = MagicMock()
    return response


def test_fetch_page_metadata_reads_og_title():
    html = """
    <html><head>
    <meta property="og:title" content="Test Article Title" />
    <meta property="og:site_name" content="Example News" />
    <meta property="article:published_time" content="2021-09-15" />
    </head><title>Ignored</title></html>
  """
    with patch("services.reference_generator.requests.get") as get:
        get.return_value = _mock_html_response(html)
        meta = fetch_page_metadata("https://example.org/article")

    assert meta["title"] == "Test Article Title"
    assert meta["organization"] == "Example News"
    assert meta["date_raw"] == "2021-09-15"


def test_generate_citation_url_harvard_from_metadata():
    html = """
    <html><head>
    <meta property="og:title" content="Climate Report" />
    <meta property="og:site_name" content="UN News" />
    <meta property="article:published_time" content="2021-09-01" />
    </head></html>
    """
    with patch("services.reference_generator.requests.get") as get:
        get.return_value = _mock_html_response(html, "https://news.example.org/story/1")
        result = generate_citation(
            mode="url",
            style="Harvard",
            url="https://news.example.org/story/1",
        )

    assert "Climate Report" in result["citation"]
    assert result["style"] == "HARVARD"
    assert result["year"] == "2021"


@pytest.mark.parametrize(
    "mode,kwargs",
    [
        ("url", {"url": ""}),
        ("doi", {"doi": ""}),
        ("isbn", {"isbn": ""}),
        ("title", {"title": ""}),
        ("paste", {"paste": ""}),
    ],
)
def test_generate_citation_requires_input(mode, kwargs):
    with pytest.raises(ValueError):
        generate_citation(mode=mode, style="APA", **kwargs)
