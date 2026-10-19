"""Deterministic ad-pixel and tag detection in a page's raw HTML (design decision 8).

A tag is found when its host, or a path on its host, appears in the HTML (script sources,
pixel images, inline loaders). No model is involved, so the same page always yields the
same signals. The kinds match the ad-activity anchors: an ad-platform pixel, a tag manager,
or analytics only.
"""

import re
from dataclasses import dataclass
from typing import Literal

TagKind = Literal["ad_pixel", "tag_manager", "analytics"]


@dataclass(frozen=True)
class Tag:
    name: str
    kind: TagKind
    # Host or host/path fragments, matched case-insensitively; the first names the host.
    patterns: tuple[str, ...]


TAGS = {
    tag.name: tag
    for tag in (
        Tag("google_ads", "ad_pixel", ("googleadservices.com", "gtag/js?id=aw-", "'aw-")),
        Tag("google_marketing_platform", "ad_pixel", ("doubleclick.net",)),
        Tag("google_adsense", "ad_pixel", ("googlesyndication.com",)),
        Tag("meta_pixel", "ad_pixel", ("connect.facebook.net", "facebook.com/tr")),
        Tag("tiktok_pixel", "ad_pixel", ("analytics.tiktok.com",)),
        Tag("reddit_pixel", "ad_pixel", ("redditstatic.com/ads", "alb.reddit.com")),
        Tag("x_pixel", "ad_pixel", ("static.ads-twitter.com", "analytics.twitter.com")),
        Tag("linkedin_insight", "ad_pixel", ("snap.licdn.com", "px.ads.linkedin.com")),
        Tag("microsoft_uet", "ad_pixel", ("bat.bing.com",)),
        Tag("pinterest_tag", "ad_pixel", ("s.pinimg.com/ct", "ct.pinterest.com")),
        Tag("snap_pixel", "ad_pixel", ("sc-static.net/scevent", "tr.snapchat.com")),
        Tag("amazon_ads", "ad_pixel", ("amazon-adsystem.com",)),
        Tag("criteo", "ad_pixel", ("static.criteo.net", "dynamic.criteo.com")),
        Tag("the_trade_desk", "ad_pixel", ("js.adsrvr.org",)),
        Tag("google_tag_manager", "tag_manager", ("googletagmanager.com/gtm.js",)),
        Tag("adobe_launch", "tag_manager", ("assets.adobedtm.com",)),
        Tag("tealium", "tag_manager", ("tags.tiqcdn.com",)),
        Tag("google_analytics", "analytics", ("google-analytics.com", "gtag/js?id=g-")),
        Tag("adobe_analytics", "analytics", ("omtrdc.net", "2o7.net")),
        Tag("hotjar", "analytics", ("static.hotjar.com",)),
    )
}
_HOST = re.compile(r"^[a-z0-9.-]+")


def detect(html: str) -> list[dict[str, str]]:
    """Every known tag the HTML loads, sorted by name, with the fragment that matched."""
    text = html.lower()
    found = []
    for tag in TAGS.values():
        for pattern in tag.patterns:
            if pattern in text:
                host = _HOST.match(tag.patterns[0])
                found.append(
                    {"tag": tag.name, "kind": tag.kind, "host": host.group() if host else ""}
                )
                break
    return sorted(found, key=lambda item: item["tag"])
