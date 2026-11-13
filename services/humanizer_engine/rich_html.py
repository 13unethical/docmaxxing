"""Protect HTML formatting around the plain-text humanizer.

Paste/DOCX → HTML in; tables stay opaque; inline bold/italic/underline/color/font become
placeholders; list markers are stripped before rewrite and always restored afterwards.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Callable

from bs4 import BeautifulSoup, NavigableString, Tag

from services.humanizer_engine.heading_utils import is_references_section_title

_LIST_MARKER = re.compile(r"^(\s*(?:[-*•+]\s|\d+[.)]\s|[a-zA-Z][.)]\s))")
_ORDINAL_WORD = re.compile(
    r"^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"one|two|three|four|five|six|seven|eight|nine|ten)\b[.,:\s]*",
    re.I,
)
_PH_OPEN = "⟦F{i}⟧"
_PH_CLOSE = "⟦/F{i}⟧"
_TABLE_TOKEN = "⟦TABLE{i}⟧"
_OPAQUE_TOKEN = "⟦OPAQUE{i}⟧"

_BLOCK_TAGS = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "blockquote", "pre"})
_INLINE_FORMAT = frozenset({"b", "strong", "i", "em", "u", "s", "strike", "del", "span", "sup", "sub"})
_STYLE_KEEP = ("color", "font-family", "font-size", "font-weight", "font-style", "text-decoration")
_ALLOWED_TAGS = frozenset(
    {
        "p", "br", "div", "span", "b", "strong", "i", "em", "u", "s", "strike", "del", "sup", "sub",
        "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td",
        "blockquote", "pre",
    }
)


@dataclass
class FormatSpan:
    index: int
    tag: str
    attrs: dict[str, str]
    inner_text: str


@dataclass
class BlockJob:
    kind: str  # prose | opaque | table
    tag: str
    attrs: dict[str, str]
    marker: str = ""
    plain: str = ""  # body only (no list marker); may contain placeholders
    html: str = ""
    spans: list[FormatSpan] = field(default_factory=list)
    ordered_list: bool | None = None


@dataclass
class RichStash:
    blocks: list[BlockJob] = field(default_factory=list)
    separator: str = "\n\n"


def sanitize_html(raw: str) -> str:
    soup = BeautifulSoup(raw or "", "html.parser")
    for tag in list(soup.find_all(True)):
        if tag.name not in _ALLOWED_TAGS:
            tag.unwrap()
            continue
        allowed: dict[str, str] = {}
        if tag.name == "span" or tag.name in _BLOCK_TAGS:
            style = _filter_style(tag.get("style") or "")
            if style:
                allowed["style"] = style
        if tag.name in ("td", "th"):
            for key in ("colspan", "rowspan"):
                if tag.get(key):
                    allowed[key] = str(tag.get(key))
        tag.attrs = allowed
    body = soup.body or soup
    return "".join(str(c) for c in body.children).strip()


def _filter_style(style: str) -> str:
    kept = []
    for part in style.split(";"):
        if ":" not in part:
            continue
        key, _, val = part.partition(":")
        key, val = key.strip().lower(), val.strip()
        if key in _STYLE_KEEP and val:
            kept.append(f"{key}: {val}")
    return "; ".join(kept)


def html_to_plaintext(html_doc: str) -> str:
    return BeautifulSoup(html_doc or "", "html.parser").get_text("\n", strip=True)


def split_list_marker(text: str) -> tuple[str, str]:
    m = _LIST_MARKER.match(text or "")
    if not m:
        return "", text or ""
    return m.group(1), text[m.end() :]


def restore_list_marker(source: str, output: str) -> str:
    """Put the source list marker back; drop a leading ordinal word the model invented."""
    marker, _ = split_list_marker(source)
    if not marker:
        return output or ""
    _, body = split_list_marker(output or "")
    body = _ORDINAL_WORD.sub("", body.lstrip(), count=1).lstrip()
    return f"{marker}{body}"


def list_marker_ok(source: str, output: str) -> bool:
    marker, _ = split_list_marker(source)
    if not marker:
        return True
    restored = restore_list_marker(source, output)
    out_marker, _ = split_list_marker(restored)
    if not out_marker:
        return False
    src_digit = bool(re.match(r"\s*\d", marker))
    out_digit = bool(re.match(r"\s*\d", out_marker))
    if src_digit != out_digit:
        return False
    return out_marker.strip()[:1] == marker.strip()[:1]


def prepare_rich(html_doc: str) -> tuple[str, RichStash]:
    cleaned = sanitize_html(html_doc)
    stash = RichStash()
    if not cleaned.strip():
        return "", stash
    soup = BeautifulSoup(cleaned, "html.parser")
    _collect_blocks(soup.body or soup, stash)
    if not stash.blocks:
        stash.blocks.append(_prose_from_fragment(cleaned, tag="p", attrs={}))
    lines: list[str] = []
    for i, job in enumerate(stash.blocks):
        if job.kind == "table":
            lines.append(_TABLE_TOKEN.format(i=i))
        elif job.kind == "opaque":
            lines.append(_OPAQUE_TOKEN.format(i=i))
        else:
            lines.append(job.plain)
    return stash.separator.join(lines), stash


def reassemble_rich(humanized_plain: str, stash: RichStash) -> str:
    if not stash.blocks:
        return f"<p>{_escape_keep_newlines(humanized_plain or '')}</p>"
    parts = (humanized_plain or "").split(stash.separator)
    out: list[str] = []
    part_i = 0
    i = 0
    while i < len(stash.blocks):
        job = stash.blocks[i]
        if job.kind in ("table", "opaque"):
            out.append(job.html)
            token = (_TABLE_TOKEN if job.kind == "table" else _OPAQUE_TOKEN).format(i=i)
            if part_i < len(parts) and parts[part_i].strip() == token:
                part_i += 1
            i += 1
            continue
        # Merge consecutive list items into one <ol>/<ul>.
        if job.tag == "li" and job.ordered_list is not None:
            items: list[str] = []
            ordered = job.ordered_list
            while i < len(stash.blocks):
                cur = stash.blocks[i]
                if cur.kind != "prose" or cur.tag != "li" or cur.ordered_list != ordered:
                    break
                chunk = parts[part_i] if part_i < len(parts) else cur.plain
                part_i += 1
                items.append(f"<li>{_prose_body(chunk, cur)}</li>")
                i += 1
            wrap = "ol" if ordered else "ul"
            out.append(f"<{wrap}>{''.join(items)}</{wrap}>")
            continue
        chunk = parts[part_i] if part_i < len(parts) else job.plain
        part_i += 1
        body = _prose_body(chunk, job)
        out.append(_wrap_block(job.tag, job.attrs, body, job.ordered_list))
        i += 1
    return "\n".join(out)


def _prose_body(chunk: str, job: BlockJob) -> str:
    if job.marker:
        _, chunk_body = split_list_marker(chunk)
        chunk_body = _ORDINAL_WORD.sub("", chunk_body.lstrip(), count=1).lstrip()
    else:
        chunk_body = chunk
    body = _restore_spans(chunk_body, job.spans)
    if job.marker:
        body = html.escape(job.marker) + body
    return body


def humanize_rich(html_doc: str, rewrite_plain: Callable[[str], str]) -> tuple[str, str]:
    """Returns (humanized_html, humanized_plaintext)."""
    plain, stash = prepare_rich(html_doc)
    if not plain.strip():
        cleaned = sanitize_html(html_doc)
        return cleaned, html_to_plaintext(cleaned)

    lines = plain.split(stash.separator)
    out_lines: list[str] = []
    for i, line in enumerate(lines):
        job = stash.blocks[i] if i < len(stash.blocks) else None
        if job and job.kind in ("table", "opaque"):
            out_lines.append(line)
            continue
        rewritten = rewrite_plain(line)
        if job and job.marker:
            body = split_list_marker(rewritten)[1].lstrip() if _LIST_MARKER.match(rewritten or "") else (rewritten or "")
            body = _ORDINAL_WORD.sub("", body, count=1).lstrip()
            out_lines.append(job.marker + body)
        else:
            out_lines.append(rewritten)
    humanized = stash.separator.join(out_lines)
    rich = reassemble_rich(humanized, stash)
    return rich, html_to_plaintext(rich)


_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_TITLE_MAX_WORDS = 12
_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]]*\s*$")


def _collect_blocks(root: Tag, stash: RichStash) -> None:
    children = [c for c in root.children if not (isinstance(c, NavigableString) and not str(c).strip())]
    i = 0
    while i < len(children):
        child = children[i]
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                stash.blocks.append(_prose_from_fragment(html.escape(text), tag="p", attrs={}))
            i += 1
            continue
        if not isinstance(child, Tag):
            i += 1
            continue
        if child.name == "table":
            stash.blocks.append(BlockJob(kind="table", tag="table", attrs={}, html=str(child)))
            i += 1
            continue
        if child.name in ("ul", "ol"):
            ordered = child.name == "ol"
            for li in child.find_all("li", recursive=False):
                stash.blocks.append(_prose_from_element(li, ordered_list=ordered))
            i += 1
            continue
        if child.name in _HEADING_TAGS:
            # Markdown/HTML headings stay verbatim (do not strip "2." off an h2 title).
            stash.blocks.append(
                BlockJob(kind="opaque", tag=child.name, attrs=dict(child.attrs or {}), html=str(child))
            )
            i += 1
            continue
        if child.name in _BLOCK_TAGS:
            text = child.get_text(" ", strip=True)
            if _is_refs_heading(text):
                # Heading + following blocks until the next real heading/section.
                chunk = [str(child)]
                i += 1
                while i < len(children):
                    nxt = children[i]
                    if isinstance(nxt, Tag) and (
                        nxt.name in _HEADING_TAGS
                        or (nxt.name in _BLOCK_TAGS and _is_section_break(nxt.get_text(" ", strip=True)))
                    ):
                        break
                    if isinstance(nxt, Tag) and nxt.name == "table":
                        break
                    if isinstance(nxt, (Tag, NavigableString)):
                        chunk.append(str(nxt) if isinstance(nxt, Tag) else html.escape(str(nxt).strip()))
                    i += 1
                stash.blocks.append(
                    BlockJob(kind="opaque", tag="div", attrs={}, html="".join(chunk))
                )
                continue
            if _is_short_title(text):
                stash.blocks.append(
                    BlockJob(kind="opaque", tag=child.name, attrs=dict(child.attrs or {}), html=str(child))
                )
                i += 1
                continue
            stash.blocks.append(_prose_from_element(child))
            i += 1
            continue
        _collect_blocks(child, stash)
        i += 1


def _is_refs_heading(text: str) -> bool:
    t = text.strip().rstrip(":")
    return bool(t) and len(t.split()) <= 3 and is_references_section_title(t)


def _is_short_title(text: str) -> bool:
    """Bare short headings pasted as <p><b>…</b></p> — keep verbatim like student titles."""
    t = text.strip()
    if not t or "\n" in t:
        return False
    # Numbered/bulleted lines are list items, not titles — still humanize.
    marker, _ = split_list_marker(t)
    if marker:
        return False
    return len(t.split()) <= _TITLE_MAX_WORDS and not _SENTENCE_END.search(t)


def _is_section_break(text: str) -> bool:
    return _is_refs_heading(text) or _is_short_title(text)


def _prose_from_element(el: Tag, ordered_list: bool | None = None) -> BlockJob:
    attrs: dict[str, str] = {}
    style = _filter_style(el.get("style") or "")
    if style:
        attrs["style"] = style
    return _prose_from_fragment(
        "".join(str(c) for c in el.children), tag=el.name, attrs=attrs, ordered_list=ordered_list
    )


def _prose_from_fragment(
    fragment: str, *, tag: str, attrs: dict[str, str], ordered_list: bool | None = None
) -> BlockJob:
    soup = BeautifulSoup(f"<div>{fragment}</div>", "html.parser")
    root = soup.div
    spans: list[FormatSpan] = []
    plain_parts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, NavigableString):
            plain_parts.append(str(node))
            return
        if not isinstance(node, Tag):
            return
        if node.name == "br":
            plain_parts.append("\n")
            return
        if node.name in _INLINE_FORMAT and _worth_protecting(node):
            idx = len(spans)
            inner = node.get_text()
            spans.append(FormatSpan(index=idx, tag=node.name, attrs=_span_attrs(node), inner_text=inner))
            plain_parts.append(_PH_OPEN.format(i=idx) + inner + _PH_CLOSE.format(i=idx))
            return
        for c in node.children:
            walk(c)

    if root:
        for c in root.children:
            walk(c)
    plain = "".join(plain_parts)
    marker, body = split_list_marker(plain)
    return BlockJob(
        kind="prose",
        tag=tag,
        attrs=attrs,
        marker=marker,
        plain=body if marker else plain,
        html="",
        spans=spans,
        ordered_list=ordered_list,
    )


def _worth_protecting(node: Tag) -> bool:
    if node.name in ("b", "strong", "i", "em", "u", "s", "strike", "del", "sup", "sub"):
        return bool(node.get_text(strip=True))
    if node.name == "span":
        return bool(_filter_style(node.get("style") or ""))
    return False


def _span_attrs(node: Tag) -> dict[str, str]:
    out: dict[str, str] = {}
    style = _filter_style(node.get("style") or "")
    if style:
        out["style"] = style
    return out


def _restore_spans(text: str, spans: list[FormatSpan]) -> str:
    if not spans:
        return _escape_keep_newlines(text)
    result = text or ""
    for span in spans:
        open_t = _PH_OPEN.format(i=span.index)
        close_t = _PH_CLOSE.format(i=span.index)
        if open_t not in result or close_t not in result:
            continue
        pattern = re.escape(open_t) + r"(.*?)" + re.escape(close_t)
        attr = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in span.attrs.items())

        def repl(m: re.Match[str], *, _span=span, _attr=attr) -> str:
            return f"<{_span.tag}{_attr}>{html.escape(m.group(1))}</{_span.tag}>"

        result = re.sub(pattern, repl, result, count=1, flags=re.DOTALL)
    # Drop leftover placeholder tokens if model mangled them
    result = re.sub(r"⟦/?F\d+⟧", "", result)
    return _escape_outside_tags(result)


def _escape_keep_newlines(text: str) -> str:
    return "<br>".join(html.escape(line) for line in (text or "").split("\n"))


def _escape_outside_tags(text: str) -> str:
    parts: list[str] = []
    last = 0
    for m in re.finditer(r"<[^>]+>", text):
        parts.append(_escape_keep_newlines(text[last:m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_escape_keep_newlines(text[last:]))
    return "".join(parts)


def _wrap_block(tag: str, attrs: dict[str, str], body: str, ordered_list: bool | None) -> str:
    if tag == "li":
        inner = f"<li>{body}</li>"
        if ordered_list is True:
            return f"<ol>{inner}</ol>"
        if ordered_list is False:
            return f"<ul>{inner}</ul>"
        return inner
    attr = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in attrs.items())
    name = tag if tag in _BLOCK_TAGS else "p"
    return f"<{name}{attr}>{body}</{name}>"
