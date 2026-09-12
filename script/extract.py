from urllib.parse import urljoin

from bs4 import BeautifulSoup

from script.models import PageContext


def extract_page(url: str, html: str) -> PageContext:
    """Static HTML extraction. Never executes JS or reads/submits input values."""
    if len(html) > 500000:
        raise ValueError("HTML too large")
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True)[:1000] if soup.title else ""
    scripts = [s.get_text()[:50000] for s in soup.find_all("script")[:20] if not s.get("src")]
    fields = []
    for node in soup.find_all("input"):
        descriptor = " ".join(str(node.get(k, "")) for k in ("type", "name", "autocomplete", "placeholder"))
        if any(
            k in descriptor.lower() for k in ("password", "otp", "one-time-code", "credit", "cc-", "身分證")
        ):
            fields.append("otp" if "otp" in descriptor or "one-time-code" in descriptor else "sensitive")
    actions = []
    from script.domains import parse_url

    for form in soup.find_all("form")[:100]:
        action = urljoin(url, form.get("action", ""))
        try:
            parse_url(action)
            actions.append(action)
        except ValueError:
            continue
    hidden = []
    for node in soup.find_all(True):
        style = str(node.get("style", "")).replace(" ", "").lower()
        if node.has_attr("hidden") or "display:none" in style or "font-size:0" in style:
            hidden.append(node.get_text(" ", strip=True))
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    return PageContext(
        url=url,
        title=title,
        text=soup.get_text(" ", strip=True)[:50000],
        scripts=scripts,
        sensitive_fields=fields[:100],
        form_actions=actions,
        hidden_text=" ".join(hidden)[:20000],
    )
