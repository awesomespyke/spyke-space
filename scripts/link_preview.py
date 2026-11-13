#!/usr/bin/env python3
"""Fetch public-page metadata for SpykeSpace; Python standard library only."""
import html
import http.client
from html.parser import HTMLParser
import ipaddress
import json
import socket
import ssl
import sys
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_BYTES = 512 * 1024
MAX_REDIRECTS = 4
TIMEOUT = 7

class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.title = []
        self.in_title = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            value = a.get("content", "").strip()
            if key and value and key not in self.meta:
                self.meta[key] = value
    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, hostname, address, port):
        super().__init__(hostname, port=port, timeout=TIMEOUT,
                         context=ssl.create_default_context())
        self.address = address
    def connect(self):
        raw = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)

def validated(url):
    parts = urlsplit(url)
    if parts.scheme.lower() != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Only public HTTPS URLs are supported")
    try:
        port = parts.port or 443
    except ValueError:
        raise ValueError("Invalid port")
    if port != 443:
        raise ValueError("Nonstandard HTTPS port")
    host = parts.hostname.rstrip(".")
    if not host or "%" in host:
        raise ValueError("Invalid hostname")
    addresses = {entry[4][0] for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("Nonpublic address")
    return parts, host, sorted(addresses)[0]

def fetch(url):
    for _ in range(MAX_REDIRECTS + 1):
        parts, host, address = validated(url)
        conn = PinnedHTTPS(host, address, 443)
        try:
            target = urlunsplit(("", "", parts.path or "/", parts.query, ""))
            conn.request("GET", target, headers={
                "Host": parts.netloc, "User-Agent": "SpykeSpace-LinkPreview/1.0",
                "Accept": "text/html", "Accept-Encoding": "identity",
                "Connection": "close"})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    return None
                url = urljoin(url, location)
                continue
            if response.status != 200:
                return None
            content_type = response.getheader("Content-Type", "")
            if "text/html" not in content_type.lower():
                return None
            if response.getheader("Content-Length") and int(response.getheader("Content-Length")) > MAX_BYTES:
                return None
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                return None
            charset = "utf-8"
            for part in content_type.split(";")[1:]:
                if part.strip().lower().startswith("charset="):
                    charset = part.split("=", 1)[1].strip().strip('"')
            try:
                page = data.decode(charset, errors="replace")
            except LookupError:
                page = data.decode("utf-8", errors="replace")
            parser = Metadata()
            parser.feed(page)
            meta = parser.meta
            title = meta.get("og:title") or meta.get("twitter:title") or "".join(parser.title).strip()
            description = meta.get("og:description") or meta.get("twitter:description") or meta.get("description") or ""
            image = meta.get("og:image") or meta.get("twitter:image") or ""
            if image:
                image = urljoin(url, html.unescape(image))
                image_parts = urlsplit(image)
                if image_parts.scheme not in ("https", "http") or not image_parts.hostname:
                    image = ""
            if not title:
                return None
            return {"url": url, "title": html.unescape(title)[:250],
                    "description": html.unescape(description)[:500], "image": image}
        finally:
            conn.close()
    return None

def preview(url):
    try:
        return fetch(url)
    except (OSError, ValueError, TimeoutError, ssl.SSLError, http.client.HTTPException):
        return None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python link_preview.py https://example.com/", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(preview(sys.argv[1]), ensure_ascii=False, indent=2))
