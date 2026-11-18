"""Protect HTML formatting around the plain-text humanizer.

Paste/DOCX → HTML in; tables stay opaque; inline bold/italic/underline/color/font become
placeholders; list markers are stripped before rewrite and always restored afterwards.
"""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from services.humanizer_engine.heading_utils import (
    is_explicit_heading_text,
    is_references_section_title,
    is_sentence_start_fragment,
)

_LIST_MARKER = re.compile(r"^(\s*(?:[-*•+]\s|\d+[.)]\s|[a-zA-Z][.)]\s))")
_ORDINAL_WORD = re.compile(
    r"^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"one|two|three|four|five|six|seven|eight|nine|ten)\b[.,:\s]*",
    re.I,
)
# Soft wraps from Word/PDF must not become <br> / fake paragraphs.
_SENTENCE_END_PROSE = re.compile(r"[.!?…][\"'”’)\]]*\s*$")
# "... study is" / "... based on" — incomplete phrase before a Capitalized continuation.
_TRAILING_FUNCTION_WORD = re.compile(
    r"\b(a|an|the|and|or|but|if|as|at|by|for|from|in|into|of|on|to|with|without|"
    r"is|are|was|were|be|been|being|have|has|had|do|does|did|will|would|"
    r"my|our|your|their|its|this|that|these|those|need|needs|needed)\s*$",
    re.I,
)
_PH_OPEN = "⟦F{i}⟧"
_PH_CLOSE = "⟦/F{i}⟧"
_TABLE_TOKEN = "⟦TABLE{i}⟧"
_OPAQUE_TOKEN = "⟦OPAQUE{i}⟧"
# Structural tokens must never appear in rewritten prose (before reassembly).
_LEAKED_OPAQUE_TABLE = re.compile(r"⟦(?:TABLE\d+|OPAQUE\d+)⟧")
# Format placeholders are stripped only AFTER span restore (or as a final safety net).
_LEAKED_FORMAT_TOKEN = re.compile(
    r"⟦/?F\d+⟧"
    r"|\[/?F\d+\]"
    r"|F\d+:\s*"  # rare: open marker mangled to "F0: " before a heading
)
_LEAKED_RICH_TOKEN = re.compile(
    r"⟦(?:/?F\d+|TABLE\d+|OPAQUE\d+)⟧"
    r"|\[/?F\d+\]"
    r"|F\d+:\s*"
)

_BLOCK_TAGS = frozenset({"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "blockquote", "pre"})
_INLINE_FORMAT = frozenset({"b", "strong", "i", "em", "u", "s", "strike", "del", "span", "sup", "sub"})
# Drop font-weight: Word/Docs often mark the whole body bold; keep real emphasis via <b>/<strong>.
_STYLE_KEEP = ("color", "font-family", "font-size", "font-style", "text-decoration")
_ALLOWED_TAGS = frozenset(
    {
        "p", "br", "div", "span", "b", "strong", "i", "em", "u", "s", "strike", "del", "sup", "sub",
        "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td",
        "blockquote", "pre",
    }
)
# Word paste puts Mso CSS in <style>; unwrap() would leak it into the essay text.
_DROP_TAGS = frozenset(
    {"style", "script", "head", "meta", "link", "title", "xml", "noscript", "iframe", "object", "embed", "svg"}
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
    # Drop first (Word <style>/<head>); unwrap second — order matters so we don't
    # touch nodes already removed with a decomposed parent.
    for tag in list(soup.find_all(_DROP_TAGS)):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    for tag in list(soup.find_all(True)):
        if tag.name not in _ALLOWED_TAGS:
            if tag.parent is not None:
                tag.unwrap()
            continue
        # Google Docs wraps paste in <b style="font-weight:normal"> — not real emphasis.
        if tag.name in ("b", "strong") and re.search(
            r"font-weight\s*:\s*(normal|400)\b", (tag.get("style") or ""), flags=re.I
        ):
            if tag.parent is not None:
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
    # Unwrap Word "select all → Bold" so body prose is not stored as <b>/<strong>.
    for tag in list(soup.find_all(["b", "strong"])):
        if tag.parent is not None and _is_blanket_bold(tag.get_text(" ", strip=True)):
            tag.unwrap()
    _demote_dense_bold(soup)
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
    """Block tags become paragraph breaks; inline tags (bold/italic) must not insert newlines.

    BeautifulSoup ``get_text("\\n")`` puts a newline around every tag — including
    ``<strong>Economics</strong>`` — which the UI then showed as fake paragraph gaps.
    """
    soup = BeautifulSoup(html_doc or "", "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    pieces: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, NavigableString):
            pieces.append(str(node))
            return
        if not isinstance(node, Tag):
            return
        if node.name in _DROP_TAGS:
            return
        block = node.name in _BLOCK_TAGS or node.name in _HEADING_TAGS or node.name == "tr"
        if block and pieces and not pieces[-1].endswith("\n"):
            pieces.append("\n")
        for child in node.children:
            walk(child)
        if block:
            pieces.append("\n")

    walk(soup.body or soup)
    text = "".join(pieces)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_list_marker(text: str) -> tuple[str, str]:
    m = _LIST_MARKER.match(text or "")
    if not m:
        return "", text or ""
    return m.group(1), text[m.end() :]


def strip_opaque_table_tokens(text: str) -> str:
    """Remove TABLE/OPAQUE markers from prose without touching bold/italic ``⟦F⟧`` placeholders."""
    if not text:
        return text or ""
    cleaned = _LEAKED_OPAQUE_TABLE.sub("", text)
    cleaned = re.sub(r"[^\S\n]{2,}", " ", cleaned)
    return cleaned


def strip_rich_tokens(text: str) -> str:
    """Remove all protect markers that leaked into visible prose (final safety net)."""
    if not text:
        return text or ""
    cleaned = _LEAKED_RICH_TOKEN.sub("", text)
    # Collapse spaces left by token removal, keep newlines.
    cleaned = re.sub(r"[^\S\n]{2,}", " ", cleaned)
    return cleaned


def unwrap_prose_newlines(text: str) -> str:
    """Join Word/PDF soft wraps inside one prose block into a single line."""
    if not text or "\n" not in text:
        return text or ""
    parts = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not parts:
        return ""
    out = parts[0]
    for nxt in parts[1:]:
        # "polari-\nization" → "polarization"
        if out.endswith("-") and nxt[:1].islower():
            out = out[:-1] + nxt
            continue
        glue = "" if out[-1:].isspace() or nxt[:1].isspace() else " "
        out = out + glue + nxt
    return out


def _prose_runs_on(text: str) -> bool:
    """True when the block looks mid-sentence (soft-wrap / split ``<p>``)."""
    flat = unwrap_prose_newlines(text or "").rstrip()
    if not flat:
        return False
    return not _SENTENCE_END_PROSE.search(flat)


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
    _coalesce_prose_fragments(stash)
    lines: list[str] = []
    for i, job in enumerate(stash.blocks):
        if job.kind == "table":
            lines.append(_TABLE_TOKEN.format(i=i))
        elif job.kind == "opaque":
            lines.append(_OPAQUE_TOKEN.format(i=i))
        else:
            lines.append(job.plain)
    return stash.separator.join(lines), stash


def _merge_prose_jobs(cur: BlockJob, nxt: BlockJob) -> BlockJob:
    shift = len(cur.spans)
    nxt_plain = nxt.plain
    nxt_spans: list[FormatSpan] = []
    for sp in sorted(nxt.spans, key=lambda s: -s.index):
        new_i = sp.index + shift
        nxt_plain = nxt_plain.replace(_PH_OPEN.format(i=sp.index), _PH_OPEN.format(i=new_i))
        nxt_plain = nxt_plain.replace(_PH_CLOSE.format(i=sp.index), _PH_CLOSE.format(i=new_i))
    for sp in nxt.spans:
        nxt_spans.append(
            FormatSpan(
                index=sp.index + shift,
                tag=sp.tag,
                attrs=sp.attrs,
                inner_text=sp.inner_text,
            )
        )
    nxt_body = nxt_plain.lstrip()
    # No space before ", ." etc. when Word split mid-sentence around bold.
    glue = ""
    if nxt_body and not nxt_body[:1].isspace() and nxt_body[:1] not in ".,;:)]}'\"”’":
        glue = " "
    return BlockJob(
        kind="prose",
        tag=nxt.tag if nxt.tag in _BLOCK_TAGS else cur.tag,
        attrs=dict(nxt.attrs or cur.attrs),
        plain=unwrap_prose_newlines(cur.plain.rstrip() + glue + nxt_body),
        html="",
        spans=list(cur.spans) + nxt_spans,
        ordered_list=nxt.ordered_list,
    )


def _should_merge_prose(cur: BlockJob, nxt: BlockJob) -> bool:
    if cur.kind != "prose" or nxt.kind != "prose":
        return False
    if cur.tag == "li" or nxt.tag == "li" or cur.marker or nxt.marker:
        return False
    if is_sentence_start_fragment(cur.plain):
        return True
    if not _prose_runs_on(cur.plain):
        return False
    nxt_flat = unwrap_prose_newlines(nxt.plain).lstrip()
    if not nxt_flat:
        return False
    nxt_start = nxt_flat[:1]
    # Lowercase / punctuation continuations are always soft wraps.
    if nxt_start.islower() or nxt_start in ".,;:)]}'\"”’":
        return True
    # Capitalized noun after a trailing function word: "study is" + "Economics".
    cur_flat = unwrap_prose_newlines(cur.plain).rstrip()
    return bool(_TRAILING_FUNCTION_WORD.search(cur_flat))


def _demote_mid_sentence_bold_heading(job: BlockJob) -> BlockJob | None:
    """Paste often wraps one bold word in its own ``<p>``; do not freeze it as a title mid-sentence."""
    if job.kind != "opaque" or job.tag in _HEADING_TAGS:
        return None
    soup = BeautifulSoup(job.html or "", "html.parser")
    root = None
    for name in ("p", "div", "blockquote"):
        root = soup.find(name)
        if root is not None:
            break
    if root is None or not _is_marked_heading_el(root):
        return None
    text = root.get_text(" ", strip=True)
    if _is_refs_heading(text):
        return None
    return _prose_from_element(root)


def _coalesce_prose_fragments(stash: RichStash) -> None:
    """Join lone ``The`` / mid-sentence soft-wrap ``<p>`` splits onto the following prose."""
    out: list[BlockJob] = []
    for cur in stash.blocks:
        if cur.kind == "prose" and "\n" in (cur.plain or ""):
            cur = BlockJob(
                kind=cur.kind,
                tag=cur.tag,
                attrs=cur.attrs,
                marker=cur.marker,
                plain=unwrap_prose_newlines(cur.plain),
                html=cur.html,
                spans=cur.spans,
                ordered_list=cur.ordered_list,
            )
        # ``<p>My field is </p><p><strong>Economics</strong></p><p>. Body…</p>``
        if (
            out
            and out[-1].kind == "prose"
            and _prose_runs_on(out[-1].plain)
            and cur.kind == "opaque"
        ):
            demoted = _demote_mid_sentence_bold_heading(cur)
            if demoted is not None:
                cur = demoted
        if out and _should_merge_prose(out[-1], cur):
            out[-1] = _merge_prose_jobs(out[-1], cur)
        else:
            out.append(cur)
    stash.blocks = out


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
    # Strip only TABLE/OPAQUE leaks here — ``⟦F⟧`` must survive until _restore_spans.
    chunk_body = unwrap_prose_newlines(strip_opaque_table_tokens(chunk_body))
    body = _restore_spans(chunk_body, job.spans)
    if job.marker:
        body = html.escape(job.marker) + body
    return body


def humanize_rich(
    html_doc: str,
    rewrite_plain: Callable[[str], str],
    *,
    max_workers: int = 16,
    on_chunk: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[str, str]:
    """Rewrite prose blocks only; tables/headings stay opaque (never sent to the model).

    Returns (humanized_html, humanized_plaintext).
    ``on_chunk`` receives each finished line as soon as it is ready.
    """
    plain, stash = prepare_rich(html_doc)
    if not plain.strip():
        cleaned = sanitize_html(html_doc)
        return cleaned, html_to_plaintext(cleaned)

    lines = plain.split(stash.separator)
    # Indices that need a model rewrite (skip opaque/table token lines).
    todo: list[int] = []
    for i, _line in enumerate(lines):
        job = stash.blocks[i] if i < len(stash.blocks) else None
        if job and job.kind in ("table", "opaque"):
            continue
        todo.append(i)

    def _rewrite_one(i: int) -> str:
        line = lines[i]
        job = stash.blocks[i] if i < len(stash.blocks) else None
        rewritten = rewrite_plain(line)
        if not isinstance(rewritten, str) or not rewritten.strip():
            rewritten = line
        # Keep ``⟦F⟧`` placeholders for reassembly; drop only structural leaks.
        rewritten = unwrap_prose_newlines(strip_opaque_table_tokens(rewritten))
        if job and job.marker:
            body = (
                split_list_marker(rewritten)[1].lstrip()
                if _LIST_MARKER.match(rewritten or "")
                else (rewritten or "")
            )
            body = _ORDINAL_WORD.sub("", body, count=1).lstrip()
            return job.marker + body
        return rewritten

    rewritten_map: dict[int, str] = {}
    rewrite_total = len(todo)
    rewrite_done = 0

    def _stream_visible(index: int, text_out: str) -> str:
        """Never leak ⟦OPAQUE⟧ / ⟦TABLE⟧ / ⟦F⟧ protect markers into the live UI."""
        job = stash.blocks[index] if index < len(stash.blocks) else None
        if job and job.kind in ("table", "opaque"):
            if job.html:
                return BeautifulSoup(job.html, "html.parser").get_text(" ", strip=True) or (job.plain or "")
            return job.plain or ""
        return strip_rich_tokens(text_out)

    def _emit(index: int, text_out: str, status: str) -> None:
        if on_chunk is None:
            return
        visible = _stream_visible(index, text_out)
        if not visible.strip() and status == "passthrough":
            # Empty heading/table shells — skip rather than flash a blank slot.
            return
        on_chunk(
            {
                "index": index,
                "text": visible,
                "status": status,
                "rewrite_total": rewrite_total,
                "rewrite_done": rewrite_done,
                "pieces": len(lines),
            }
        )

    todo_set = set(todo)
    for i, line in enumerate(lines):
        if i in todo_set:
            # Original line while this block rewrites — UI morphs it when ready.
            _emit(i, line, "pending")
        else:
            _emit(i, line, "passthrough")

    if todo:
        workers = max(1, min(max_workers, len(todo)))
        if workers == 1:
            for i in todo:
                rewritten_map[i] = _rewrite_one(i)
                rewrite_done += 1
                _emit(i, rewritten_map[i], "ready")
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_rewrite_one, i): i for i in todo}
                for fut in as_completed(futures):
                    i = futures[fut]
                    rewritten_map[i] = fut.result()
                    rewrite_done += 1
                    _emit(i, rewritten_map[i], "ready")

    out_lines: list[str] = []
    for i, line in enumerate(lines):
        out_lines.append(rewritten_map[i] if i in rewritten_map else line)
    humanized = stash.separator.join(out_lines)
    rich = reassemble_rich(humanized, stash)
    # Final safety: never return protect markers to the client.
    rich = strip_rich_tokens(rich)
    text = strip_rich_tokens(html_to_plaintext(rich))
    return rich, text


_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_TITLE_MAX_WORDS = 12


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
                        or (nxt.name in _BLOCK_TAGS and _is_section_break(nxt))
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
            if _is_marked_heading_el(child):
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


def _is_marked_heading_el(el: Tag) -> bool:
    """Keep verbatim only when the block is explicitly marked as a heading.

    - References / Bibliography label
    - whole paragraph is a single ``<b>`` / ``<strong>`` (short, no sentence end)
    Plain short ``<p>Methodology</p>`` is prose — no length guessing.
    """
    text = el.get_text(" ", strip=True)
    if not text or "\n" in text:
        return False
    marker, _ = split_list_marker(text)
    if marker:
        return False
    if _is_refs_heading(text):
        return True
    # Entire block = one bold/strong node (optional whitespace-only siblings).
    significant: list[Tag] = []
    for c in el.children:
        if isinstance(c, NavigableString):
            if str(c).strip():
                return False
            continue
        if isinstance(c, Tag):
            if c.name in ("b", "strong"):
                significant.append(c)
            else:
                return False
    if len(significant) != 1:
        return False
    inner = significant[0].get_text(" ", strip=True)
    return is_explicit_heading_text(f"**{inner}**", max_words=_TITLE_MAX_WORDS)


def _is_section_break(el_or_text: Tag | str) -> bool:
    if isinstance(el_or_text, Tag):
        return _is_marked_heading_el(el_or_text)
    return _is_refs_heading(el_or_text) or is_explicit_heading_text(el_or_text, max_words=_TITLE_MAX_WORDS)


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
    plain = unwrap_prose_newlines("".join(plain_parts))
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


def _is_blanket_bold(text: str) -> bool:
    """Word 'select all → Bold' wraps whole paragraphs; those are body, not emphasis."""
    t = (text or "").strip()
    if not t:
        return False
    if len(t) > 80:
        return True
    # A sentence-bearing run is prose even when short enough to look like a title.
    return len(t) > 40 and bool(re.search(r"[.!?]\s", t))


def _is_heading_like_bold(tag: Tag) -> bool:
    """Short bold that is the whole block — keep as a title, not dense-body noise."""
    text = tag.get_text(" ", strip=True)
    if not text or len(text) > 80 or re.search(r"[.!?]", text):
        return False
    parent = tag.parent
    if not isinstance(parent, Tag) or parent.name not in _BLOCK_TAGS:
        return False
    return parent.get_text(" ", strip=True) == text


def _demote_dense_bold(soup: BeautifulSoup) -> None:
    """If almost every character is inside <b>/<strong>, Word split-bolded the body — unwrap."""
    root = soup.body or soup
    total = len(root.get_text(" ", strip=True))
    if total < 40:
        return
    bolds = list(root.find_all(["b", "strong"]))
    if not bolds:
        return
    bold_len = sum(len(t.get_text(" ", strip=True)) for t in bolds)
    if bold_len / total < 0.85:
        return
    for tag in bolds:
        if tag.parent is None or _is_heading_like_bold(tag):
            continue
        tag.unwrap()


def _worth_protecting(node: Tag) -> bool:
    if node.name in ("b", "strong"):
        text = node.get_text(strip=True)
        return bool(text) and not _is_blanket_bold(text)
    if node.name in ("i", "em", "u", "s", "strike", "del", "sup", "sub"):
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
    flat = unwrap_prose_newlines(text or "")
    if not spans:
        return html.escape(flat)
    result = flat
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
    # Drop leftover format placeholders if the model mangled them
    result = _LEAKED_FORMAT_TOKEN.sub("", result)
    result = re.sub(r"[^\S\n]{2,}", " ", result)
    return _escape_outside_tags(result)


def _escape_keep_newlines(text: str) -> str:
    """Legacy helper: prose path unwraps first; leftover newlines become spaces, not ``<br>``."""
    return html.escape(unwrap_prose_newlines(text or ""))


def _escape_outside_tags(text: str) -> str:
    parts: list[str] = []
    last = 0
    for m in re.finditer(r"<[^>]+>", text):
        parts.append(html.escape(unwrap_prose_newlines(text[last:m.start()])))
        parts.append(m.group(0))
        last = m.end()
    parts.append(html.escape(unwrap_prose_newlines(text[last:])))
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
