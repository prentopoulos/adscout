"""Page text and the company-site pages enrichment reads (design decision 8).

Enrichment reads at most three pages of a company's own site: the home page, a newsroom or
press page, and a store or shipping page, chosen by code from the home page's same-site
links. Text is taken from the HTML without scripts, styles or hidden templates.
"""

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from adscout.sources.urls import on_site

SKIP = {"script", "style", "noscript", "template", "svg", "head"}
BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "section", "article"}
NEWS_WORDS = ("newsroom", "press", "news", "media", "blog", "announcement")
STORE_WORDS = ("shipping", "where-to-buy", "where to buy", "store", "shop", "countries", "region")


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._skip = 0
        self._href: str | None = None
        self._anchor: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP:
            self._skip += 1
        elif tag in BLOCK:
            self.parts.append("\n")
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._anchor = []

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP and self._skip:
            self._skip -= 1
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._anchor).split())))
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self.parts.append(data)
        if self._href is not None:
            self._anchor.append(data)


def read(html: str) -> _Reader:
    reader = _Reader()
    reader.feed(html)
    reader.close()
    return reader


def text_of(html: str) -> str:
    """Visible text, one line per block, whitespace collapsed."""
    lines = ("".join(read(html).parts)).splitlines()
    return "\n".join(" ".join(line.split()) for line in lines if line.strip())


def site_links(html: str, base_url: str, domain: str) -> list[tuple[str, str]]:
    """Same-site http(s) links as (absolute URL without fragment, anchor text), in order."""
    seen: set[str] = set()
    found = []
    for href, anchor in read(html).links:
        url = urljoin(base_url, href.strip())
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not on_site(url, domain):
            continue
        clean = urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))
        if clean not in seen:
            seen.add(clean)
            found.append((clean, anchor))
    return found


def pick_pages(html: str, base_url: str, domain: str) -> list[str]:
    """The newsroom or press page and the store or shipping page, when the home page links
    them; at most one of each, so enrichment reads at most three pages in all."""
    links = site_links(html, base_url, domain)
    chosen: list[str] = []
    for words in (NEWS_WORDS, STORE_WORDS):
        for url, anchor in links:
            haystack = f"{urlsplit(url).path.lower()} {anchor.lower()}"
            if (
                url not in chosen
                and url.rstrip("/") != base_url.rstrip("/")
                and any(word in haystack for word in words)
            ):
                chosen.append(url)
                break
    return chosen
