import re
import asyncio
import httpx
from urllib.parse import urlparse, urljoin

TLD_FALLBACKS = ['.eu', '.com', '.de', '.net', '.org', '.at', '.ch', '.io']

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

DISCOVERY_KEYWORDS = re.compile(
    r'impressum|kontakt|contact|about|ueber-uns|über-uns|legal|datenschutz|privacy|imprint',
    re.IGNORECASE,
)

PRIORITY_PAGES = [
    '/impressum', '/Impressum', '/impressum.html',
    '/de/impressum', '/de/impressum.html', '/en/imprint', '/imprint',
]
SECONDARY_PAGES = [
    '/kontakt', '/Kontakt', '/kontakt.html',
    '/contact', '/Contact', '/contact.html',
    '/ueber-uns', '/about', '/en/contact', '/de/kontakt',
]

PRIORITY_PREFIXES = (
    'info@', 'kontakt@', 'contact@', 'sales@', 'hello@',
    'mail@', 'post@', 'office@', 'service@', 'anfrage@',
    'vertrieb@', 'handel@', 'bestellung@', 'export@',
)

IGNORE_SUFFIXES = ('.png', '.jpg', '.gif', '.svg', '.css', '.js', '.webp', '.ico')
IGNORE_CONTAINS = (
    'example.', 'sentry', 'wixpress.', 'schema.org',
    'placeholder', '@2x', 'yourdomain', 'domain.com', 'test@', 'user@',
    'noreply', 'no-reply', 'donotreply', 'bounce', 'mailer-daemon',
    'aphixsoftware', 'bugsnag', 'rollbar', 'datadog',
)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Cache-Control': 'max-age=0',
}

PAGE_LABELS = {
    '/impressum': 'Impressum', '/Impressum': 'Impressum',
    '/impressum.html': 'Impressum', '/de/impressum': 'Impressum (DE)',
    '/de/impressum.html': 'Impressum (DE)', '/en/imprint': 'Imprint (EN)',
    '/imprint': 'Imprint',
    '/kontakt': 'Kontakt', '/Kontakt': 'Kontakt', '/kontakt.html': 'Kontakt',
    '/contact': 'Contact', '/Contact': 'Contact', '/contact.html': 'Contact',
    '/ueber-uns': 'Über uns', '/about': 'About',
    '/en/contact': 'Contact (EN)', '/de/kontakt': 'Kontakt (DE)',
    '/': 'Homepage',
}

# Short timeout just for checking if a domain responds
PROBE_TIMEOUT = httpx.Timeout(5.0)
# Timeout for fetching full page content
FETCH_TIMEOUT = httpx.Timeout(8.0)


def _decode_cf_email(encoded: str) -> str:
    key = int(encoded[:2], 16)
    return ''.join(chr(int(encoded[i:i+2], 16) ^ key) for i in range(2, len(encoded), 2))


def _deobfuscate(text: str) -> str:
    text = re.sub(r'\s*\[at\]\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(at\)\s*', '@', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+at\s+', '@', text)
    text = re.sub(r'\s*\[dot\]\s*', '.', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\(dot\)\s*', '.', text, flags=re.IGNORECASE)
    text = text.replace('&#64;', '@').replace('%40', '@')
    text = text.replace('&#46;', '.').replace('%2E', '.')
    return text


def _extract_emails(html: str) -> list[str]:
    result = set()
    for m in re.finditer(r'data-cfemail="([0-9a-f]+)"', html, re.IGNORECASE):
        try:
            result.add(_decode_cf_email(m.group(1)).lower())
        except Exception:
            pass
    for e in EMAIL_REGEX.findall(_deobfuscate(html)):
        e = e.lower().strip('.,;:')
        if any(e.endswith(s) for s in IGNORE_SUFFIXES):
            continue
        if any(s in e for s in IGNORE_CONTAINS):
            continue
        if not re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', e):
            continue
        if re.match(r'^[0-9a-f]{16,}$', e.split('@')[0]):
            continue
        result.add(e)
    return list(result)


def _rank(email: str) -> int:
    return 0 if email.startswith(PRIORITY_PREFIXES) else 1


def _discover_links(html: str, base: str) -> list[tuple[str, str]]:
    bare_domain = urlparse(base).netloc.removeprefix('www.')
    found, seen_paths = [], set()
    for m in re.finditer(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
        href = m.group(1).strip()
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if not DISCOVERY_KEYWORDS.search(href) and not DISCOVERY_KEYWORDS.search(text):
            continue
        full_url = urljoin(base, href)
        parsed = urlparse(full_url)
        if parsed.netloc and parsed.netloc.removeprefix('www.') != bare_domain:
            continue
        path = parsed.path.rstrip('/')
        if path in seen_paths or not path:
            continue
        seen_paths.add(path)
        found.append((full_url, text[:40] if text else path))
        if len(found) >= 8:
            break
    return found


async def _probe(client: httpx.AsyncClient, url: str) -> int:
    try:
        r = await client.get(url, headers=HEADERS, timeout=PROBE_TIMEOUT)
        return r.status_code
    except Exception:
        return 0


async def _fetch_page(client: httpx.AsyncClient, url: str) -> tuple[list[str], str]:
    try:
        r = await client.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT)
        if r.status_code == 200:
            return _extract_emails(r.text), r.text
    except Exception:
        pass
    return [], ''


async def _fetch_pages_parallel(client: httpx.AsyncClient, urls: list[str]) -> list[tuple[list[str], str]]:
    """Fetch multiple pages concurrently."""
    return await asyncio.gather(*[_fetch_page(client, url) for url in urls])


async def _resolve_base(client: httpx.AsyncClient, base: str) -> tuple[str, str | None]:
    host = urlparse(base).netloc
    www_base = f'https://www.{host}' if not host.startswith('www.') else f'https://{host[4:]}'

    # Probe both variants in parallel
    statuses = await asyncio.gather(
        _probe(client, base + '/'),
        _probe(client, www_base + '/'),
    )

    for candidate, status in [(base, statuses[0]), (www_base, statuses[1])]:
        if 0 < status < 500 and status != 403:
            return candidate, None

    if 403 in statuses:
        canonical = www_base if not host.startswith('www.') else base
        return canonical, "Bot protection (403) — website blocks automated scrapers"

    # Truly unreachable — try TLD variants in parallel
    bare = host.removeprefix('www.')
    dot = bare.rfind('.')
    if dot != -1:
        stem, current_tld = bare[:dot], bare[dot:]
        candidates = [
            f'https://{stem}{tld}'
            for tld in TLD_FALLBACKS if tld != current_tld
        ] + [
            f'https://www.{stem}{tld}'
            for tld in TLD_FALLBACKS if tld != current_tld
        ]
        tld_statuses = await asyncio.gather(*[_probe(client, c + '/') for c in candidates])
        for candidate, status in zip(candidates, tld_statuses):
            if 0 < status < 500:
                return candidate, None

    return base, "Website unreachable"


async def scrape_website_emails(url: str) -> dict:
    if not url:
        return {"emails": [], "resolved_base": None, "error": "No URL provided"}

    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url

    domain = urlparse(url).netloc or url.split('/')[0]
    base = f'https://{domain}'
    found: dict[str, dict] = {}

    async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
        base, reach_error = await _resolve_base(client, base)

        if reach_error and 'Bot protection' in reach_error:
            return {"emails": [], "resolved_base": base, "error": reach_error}

        # Phase 1 — fetch all priority pages in parallel
        priority_urls = [base + p for p in PRIORITY_PAGES]
        results = await _fetch_pages_parallel(client, priority_urls)
        for page, (emails, _) in zip(PRIORITY_PAGES, results):
            for e in emails:
                if e not in found:
                    found[e] = {"source_page": base + page, "page_label": PAGE_LABELS.get(page, page)}

        has_priority = any(e.startswith(PRIORITY_PREFIXES) for e in found)

        # Phase 2 — discover links from homepage if still no priority email
        if not has_priority:
            _, homepage_html = await _fetch_page(client, base + '/')
            if homepage_html:
                disc_links = _discover_links(homepage_html, base)
                tried_paths = set(PRIORITY_PAGES)
                disc_links = [(u, l) for u, l in disc_links
                              if urlparse(u).path.rstrip('/') not in tried_paths]
                if disc_links:
                    disc_results = await _fetch_pages_parallel(client, [u for u, _ in disc_links])
                    for (disc_url, disc_label), (emails, _) in zip(disc_links, disc_results):
                        path = urlparse(disc_url).path.rstrip('/')
                        for e in emails:
                            if e not in found:
                                found[e] = {
                                    "source_page": disc_url,
                                    "page_label": PAGE_LABELS.get(path, disc_label),
                                }

        # Phase 3 — secondary pages in parallel if still no priority email
        if not any(e.startswith(PRIORITY_PREFIXES) for e in found):
            sec_urls = [base + p for p in SECONDARY_PAGES]
            results = await _fetch_pages_parallel(client, sec_urls)
            for page, (emails, _) in zip(SECONDARY_PAGES, results):
                for e in emails:
                    if e not in found:
                        found[e] = {"source_page": base + page, "page_label": PAGE_LABELS.get(page, page)}

        # Phase 4 — homepage last resort
        if not found:
            emails, _ = await _fetch_page(client, base + '/')
            for e in emails:
                found[e] = {"source_page": base + '/', "page_label": "Homepage"}

    if not found:
        error = reach_error or "No email found — site may use JS-only rendering"
        return {"emails": [], "resolved_base": base, "error": error}

    ranked = sorted(found.items(), key=lambda x: (_rank(x[0]), x[0]))
    return {"emails": [{"email": e, **meta} for e, meta in ranked], "resolved_base": base, "error": None}
