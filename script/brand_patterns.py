"""Conservative token matching; never infer a scam merely from a hyphen or TLD."""

import re

from script.domains import brands, host, matches_domain


def transposed(token: str, expected: str) -> bool:
    if len(token) != len(expected) or len(token) < 4:
        return False
    return any(
        token == expected[:i] + expected[i + 1] + expected[i] + expected[i + 2 :]
        for i in range(len(expected) - 1)
        if expected[i] != expected[i + 1]
    )


def brand_patterns(url: str) -> list[dict]:
    hostname = host(url)
    found = []
    for brand in brands():
        if any(matches_domain(hostname, d) for d in brand["domains"]):
            continue
        for label in hostname.split("."):
            # Full label token only, not arbitrary substrings in names like "fetcetera".
            match = re.fullmatch(r"([a-z]{4,20})(?:-?([0-9]{1,6}))?", label)
            if not match:
                continue
            token, serial = match.groups()
            if any(
                token == expected or transposed(token, expected)
                for expected in brand.get("domain_tokens", [])
            ):
                found.append(
                    {
                        "id": "brand_lookalike_" + brand["id"],
                        "detail": f"網址片段「{label}」近似{brand['name']}品牌名稱，"
                        f"但主機不在官方網域名單；請自行前往 https://{brand['domains'][0]}/ 查詢，勿在此輸入付款資料或驗證碼",
                        "weight": 35 if serial else 25,
                    }
                )
                break
    return found
