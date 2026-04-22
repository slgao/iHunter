import re
import asyncio
import dns.resolver
import dns.exception

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


def _check_format(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email.strip()))


def _check_mx(domain: str) -> bool:
    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=5)
        return len(answers) > 0
    except (dns.exception.DNSException, Exception):
        return False


async def verify_email(email: str) -> dict:
    """
    Returns: { valid: bool, status: 'valid'|'invalid_format'|'invalid_domain'|'unverifiable', detail: str }
    """
    email = email.strip().lower()

    if not email:
        return {"valid": False, "status": "invalid_format", "detail": "Empty email"}

    if not _check_format(email):
        return {"valid": False, "status": "invalid_format", "detail": "Invalid email format"}

    domain = email.split("@")[1]

    # Run DNS lookup in thread pool to avoid blocking the event loop
    try:
        has_mx = await asyncio.get_event_loop().run_in_executor(None, _check_mx, domain)
    except Exception:
        return {"valid": False, "status": "unverifiable", "detail": "DNS lookup failed"}

    if has_mx:
        return {"valid": True, "status": "valid", "detail": f"Domain {domain} has valid MX records"}
    else:
        return {"valid": False, "status": "invalid_domain", "detail": f"Domain {domain} has no MX records"}
