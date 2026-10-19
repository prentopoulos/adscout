"""Egress rules every outside request obeys (design decision 28), and site membership.

A URL is refused unless it is http(s), names a host by DNS name (no IP literal, no single-
label or local name), carries no credentials, keeps its query string short and, when a
resolver is given, resolves only to public addresses. Provenance (which URLs a research
worker may fetch at all) is the research tools' rule, built on top of this one.
"""

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

MAX_QUERY_LENGTH = 200
LOCAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet")

Resolver = Callable[[str], Iterable[str]]


def system_resolver(host: str) -> list[str]:
    return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, None)})


def egress_problem(url: str, resolver: Resolver | None = None) -> str | None:
    """Why this URL may not be requested, or None if it may."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as error:
        return f"not a valid URL: {error}"
    if parts.scheme not in ("http", "https"):
        return f"scheme {parts.scheme or '(none)'} is not http or https"
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        return "the URL carries credentials"
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        return "the URL has no host"
    if _is_ip(host):
        return "the host is an IP address"
    if "." not in host or host == "localhost" or host.endswith(LOCAL_SUFFIXES):
        return f"{host} is not a public DNS name"
    if port is not None and port not in (80, 443):
        return f"port {port} is not a web port"
    if len(parts.query) > MAX_QUERY_LENGTH:
        return f"the query string is longer than {MAX_QUERY_LENGTH} characters"
    if resolver is not None:
        try:
            addresses = list(resolver(host))
        except OSError as error:
            return f"{host} did not resolve: {error}"
        private = [address for address in addresses if not _public(address)]
        if private or not addresses:
            return f"{host} resolves to a non-public address"
    return None


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").rstrip(".").lower().removeprefix("www.")


def on_site(url: str, domain: str) -> bool:
    """Whether the URL's host is the site's domain or one of its subdomains."""
    host = (urlsplit(url).hostname or "").rstrip(".").lower()
    return host == domain or host.endswith(f".{domain}")


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def _public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return ip.is_global and not ip.is_multicast


# Third-party sites never searched or read: social networks and people-search or contact
# databases, so research stays on company-level sources (design decision 11; PROJECT.md §5).
BLOCKED_DOMAINS = (
    "beenverified.com",
    "facebook.com",
    "fastpeoplesearch.com",
    "instagram.com",
    "intelius.com",
    "linkedin.com",
    "mylife.com",
    "peoplefinders.com",
    "radaris.com",
    "rocketreach.co",
    "spokeo.com",
    "tiktok.com",
    "truepeoplesearch.com",
    "twitter.com",
    "whitepages.com",
    "x.com",
    "zoominfo.com",
)
