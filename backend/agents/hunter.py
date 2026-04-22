import httpx
from urllib.parse import urlparse


def _extract_domain(website: str) -> str:
    website = website.strip()
    if not website.startswith("http"):
        website = "https://" + website
    return urlparse(website).netloc.lstrip("www.")


async def hunter_find_email(domain_or_url: str, api_key: str) -> dict:
    """
    Uses Hunter.io domain-search to find emails for a company domain.
    Returns { emails: [...], error: str|None }
    Free tier: 25 searches/month — https://hunter.io
    """
    domain = _extract_domain(domain_or_url)
    url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={api_key}&limit=5"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            data = r.json()

        if r.status_code != 200:
            return {"emails": [], "error": data.get("errors", [{}])[0].get("details", "Hunter API error")}

        emails_data = data.get("data", {}).get("emails", [])
        emails = []
        for item in emails_data:
            e = item.get("value", "")
            if e:
                emails.append({
                    "email": e,
                    "type": item.get("type", ""),        # personal or generic
                    "confidence": item.get("confidence", 0),
                    "first_name": item.get("first_name"),
                    "last_name": item.get("last_name"),
                    "position": item.get("position"),
                })

        # Sort: generic (info@) first, then by confidence
        emails.sort(key=lambda x: (0 if x["type"] == "generic" else 1, -x["confidence"]))
        return {"emails": emails, "error": None}

    except Exception as e:
        return {"emails": [], "error": str(e)}
