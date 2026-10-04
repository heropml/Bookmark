# -*- coding: utf-8 -*-
"""Bookmark file formats: Netscape HTML exports, Chromium JSON and Safari plists.

Every reader returns the items the page shows: ``{"title", "href", "path", "group", "host"}``.
"""
from __future__ import annotations

import html
import json
import plistlib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


def host_of(href: str) -> str:
    # Drop "user:password@" so credentials are neither shown nor sent to icon services.
    host = urlparse(href).netloc.rpartition("@")[2].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def norm_url(href: str) -> str:
    p = urlparse(href.strip())
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/") or "/"
    params = f";{p.params}" if p.params else ""
    query = f"?{p.query}" if p.query else ""
    fragment = f"#{p.fragment}" if p.fragment else ""
    return f"{p.scheme.lower()}://{host}{path}{params}{query}{fragment}"


class _NetscapeBookmarkParser(HTMLParser):
    """Read a Netscape bookmark export by tags, so line breaks and attribute order do not matter."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[dict] = []
        # One entry per open <DL>: the folder name it belongs to, "" when it adds no category.
        self.stack: list[str] = []
        self.pending: str | None = None  # folder named by the last <H3>, waiting for its <DL>
        self.folder: dict | None = None  # <H3> being read
        self.link: dict | None = None  # <A> being read

    def handle_starttag(self, tag, attrs):
        # Exports may leave <A> unclosed; the next entry or a <DD> description ends its title.
        if tag in ("a", "h3", "dt", "dd", "dl"):
            self.finish_link()
        if tag == "h3":
            self.pending = None
            # Browsers mark their toolbar folder in exports; its localized name is not a category.
            self.folder = {"toolbar": any(
                name == "personal_toolbar_folder" and (value or "").lower() == "true"
                for name, value in attrs), "text": []}
        elif tag == "a":
            self.pending = None
            href = next((value for name, value in attrs if name == "href"), None)
            self.link = {"href": href, "text": []} if href and href.strip() else None
        elif tag == "dl":
            self.stack.append(self.pending or "")
            self.pending = None

    def handle_endtag(self, tag):
        if tag == "a":
            self.finish_link()
        elif tag == "h3" and self.folder is not None:
            name = "".join(self.folder["text"]).strip()
            # An empty name keeps </DL> nesting balanced but leaves the toolbar out of paths.
            self.pending = "" if self.folder["toolbar"] else name
            self.folder = None
        elif tag == "dl":
            self.finish_link()
            self.pending = None
            if self.stack:
                self.stack.pop()

    def handle_data(self, data):
        if self.link is not None:
            self.link["text"].append(data)
        elif self.folder is not None:
            self.folder["text"].append(data)

    def finish_link(self):
        link, self.link = self.link, None
        if link is None:
            return
        href = link["href"].strip()
        title = "".join(link["text"]).strip()
        parts = [name for name in self.stack if name and name != "\u4e66\u7b7e\u680f"]
        other = "\u5176\u4ed6"
        self.items.append({
            "title": title or host_of(href),
            "href": href,
            "path": "/".join(parts) or other,
            "group": parts[0] if parts else other,
            "host": host_of(href),
        })

    def close(self):
        super().close()
        self.finish_link()


def parse_html(text: str) -> list[dict]:
    parser = _NetscapeBookmarkParser()
    parser.feed(text)
    parser.close()
    return parser.items


def dedupe_items(items: list[dict]) -> tuple[list[dict], int]:
    """Keep the first copy of each address; the source file itself is never rewritten."""
    seen: set[str] = set()
    kept = []
    for item in items:
        key = norm_url(item["href"])
        if key not in seen:
            seen.add(key)
            kept.append(item)
    return kept, len(items) - len(kept)


def parse_chrome(path: Path) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    roots = document.get("roots")
    if not isinstance(roots, dict):
        raise SystemExit(f"invalid Chrome bookmarks file: {path}")
    items = []
    other = "\u5176\u4ed6"

    def walk(node: dict, parents: list[str]) -> None:
        if node.get("type") == "url":
            href = str(node.get("url", "")).strip()
            if not href:
                return
            title = str(node.get("name", "")).strip()
            path_name = "/".join(parents) or other
            items.append(
                {
                    "title": title or host_of(href),
                    "href": href,
                    "path": path_name,
                    "group": parents[0] if parents else other,
                    "host": host_of(href),
                }
            )
            return
        if node.get("type") != "folder":
            return
        name = str(node.get("name", "")).strip()
        next_parents = parents + [name] if name else parents
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, next_parents)

    for root_name, root in roots.items():
        if not isinstance(root, dict):
            continue
        parents = []
        if root_name != "bookmark_bar":
            name = str(root.get("name", "")).strip()
            if name:
                parents.append(name)
        for child in root.get("children") or []:
            if isinstance(child, dict):
                walk(child, parents)
    return items


def parse_safari(path: Path) -> list[dict]:
    try:
        with path.open("rb") as stream:
            document = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise SystemExit(f"invalid Safari bookmarks file: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise SystemExit(f"invalid Safari bookmarks file: {path}")

    items = []
    other = "\u5176\u4ed6"
    folder_names = {
        "BookmarksBar": "\u4e2a\u4eba\u6536\u85cf",
        "BookmarksMenu": "\u4e66\u7b7e\u83dc\u5355",
        "ReadingList": "\u9605\u8bfb\u5217\u8868",
    }

    def walk(node: dict, parents: list[str]) -> None:
        href = str(node.get("URLString", "")).strip()
        if href:
            uri = node.get("URIDictionary")
            title = str(uri.get("title", "")).strip() if isinstance(uri, dict) else ""
            title = title or str(node.get("Title", "")).strip()
            path_name = "/".join(parents) or other
            items.append(
                {
                    "title": title or host_of(href),
                    "href": href,
                    "path": path_name,
                    "group": parents[0] if parents else other,
                    "host": host_of(href),
                }
            )
            return

        children = node.get("Children")
        if not isinstance(children, list):
            return
        name = str(node.get("Title", "")).strip()
        name = folder_names.get(name, name)
        next_parents = parents + [name] if name else parents
        for child in children:
            if isinstance(child, dict):
                walk(child, next_parents)

    for child in document.get("Children") or []:
        if isinstance(child, dict):
            walk(child, [])
    return items


def render_bookmarks_html(items: list[dict]) -> str:
    root = {"children": [], "folders": {}}
    for item in items:
        node = root
        for name in filter(None, item["path"].split("/")):
            folder = node["folders"].get(name)
            if folder is None:
                folder = {"name": name, "children": [], "folders": {}}
                node["folders"][name] = folder
                node["children"].append(("folder", folder))
            node = folder
        node["children"].append(("url", item))

    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
    ]

    def emit(node: dict, level: int) -> None:
        pad = "    " * level
        lines.append(pad + "<DL><p>")
        for kind, child in node["children"]:
            if kind == "folder":
                lines.append(pad + "    <DT><H3>" + html.escape(child["name"]) + "</H3>")
                emit(child, level + 1)
            else:
                title = html.escape(child["title"])
                href = html.escape(child["href"], quote=True)
                lines.append(pad + '    <DT><A HREF="' + href + '">' + title + "</A>")
        lines.append(pad + "</DL><p>")

    emit(root, 0)
    return "\n".join(lines) + "\n"
