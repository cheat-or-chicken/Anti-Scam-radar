import re
from difflib import SequenceMatcher
from urllib.parse import unquote, urlsplit

from script.domains import brands, host, matches_domain, same_site, trusted
from script.models import Download, LayerResult, PageContext, Signal, result


def sig(id, detail, weight=15, observed=False, hard=False):
    return Signal(
        id=id, detail=detail, weight=weight, grade="observed" if observed else "inferred", hard=hard
    )


def gate(ctx: PageContext) -> str:
    # Never bypass local behavior/download checks, even on maintained trusted domains.
    if (
        ctx.sensitive_fields
        or ctx.network_trace
        or ctx.downloads
        or ctx.redirects
        or ctx.hidden_text
        or ctx.delayed_sensitive_injection
        or (ctx.domain_age_days is not None and ctx.domain_age_days < 30)
    ):
        return "analyze_full"
    return "skip" if trusted(ctx.url) else "analyze_light"


def verify_l0(ctx):
    return result("L0", [], available=True).model_copy(update={"user_facing_reason": gate(ctx)})


def verify_l1(ctx):
    signals = []
    chain = [*ctx.redirects, ctx.url]
    if any(urlsplit(a).scheme == "https" and urlsplit(b).scheme == "http" for a, b in zip(chain, chain[1:])):
        signals.append(sig("https_downgrade", "導覽鏈從 HTTPS 降級為 HTTP", 20, True))
    if sum(not same_site(a, b) for a, b in zip(chain, chain[1:])) >= 3:
        signals.append(sig("many_redirects", "導覽鏈跨越至少三個不同網站", 15, True))
    for url in dict.fromkeys(chain):
        hostname = host(url)
        if "xn--" in hostname:
            signals.append(sig("idn_domain", "網址使用國際化網域，請確認字形是否符合預期", 5))
        if hostname.endswith((".top", ".xyz", ".cyou")):
            signals.append(sig("unusual_tld", "網址使用需額外核對的頂級網域", 5))
        for brand in brands():
            if any(d in hostname and not matches_domain(hostname, d) for d in brand["domains"]):
                signals.append(
                    sig("official_domain_embedded", "官方網域文字被嵌入另一個網站的網址中", 40, True)
                )
    return result("L1", list({s.id: s for s in signals}.values()))


def verify_l2(ctx):
    signals = []
    # Title / explicit claim only: mentioning a government agency in a news article is not a claim.
    claims = (ctx.claimed_brand or "") + " " + ctx.title
    for brand in brands():
        if any(alias in claims for alias in brand["aliases"]):
            if not any(matches_domain(host(ctx.url), d) for d in brand["domains"]):
                signals.append(
                    sig(
                        "brand_domain_mismatch",
                        f"頁面標題或宣稱提到{brand['name']}，網址不在已維護的官方名單",
                        40,
                    )
                )
    return result("L2", signals, available=bool(claims.strip()))


def verify_l3(ctx):
    signals = []
    # Restrict hard findings to actual behavior (L4); semantic requests remain inferred.
    for sentence in re.split(r"[。！？\n]", ctx.text):
        if re.search(r"不要|切勿|請勿|不會|勿將|防詐|詐騙案例", sentence):
            continue
        if re.search(r"(?:安裝|下載).{0,25}(?:AnyDesk|TeamViewer|QuickSupport)", sentence, re.IGNORECASE):
            signals.append(sig("remote_control_request", "文案要求安裝遠端控制軟體，請核對聯絡對象", 45))
        if re.search(
            r"(?:提供|告知|傳送|回傳).{0,15}(?:OTP|驗證碼|網銀密碼|提款卡密碼).{0,15}(?:客服|專員|我們)",
            sentence,
            re.IGNORECASE,
        ):
            signals.append(sig("credential_relay_request", "文案要求將驗證碼或密碼交給他人", 55))
        if re.search(r"ATM.{0,20}解除分期|保證獲利|穩賺不賠", sentence, re.IGNORECASE):
            signals.append(sig("financial_manipulation", "文案含 ATM 解除分期或保證獲利話術", 40))
        if re.search(r"(?:罰單|罰鍰|通行費).{0,30}(?:立即|逾期|限時|繳納)", sentence):
            signals.append(
                sig("government_payment_pressure", "頁面催促繳納交通費用，請從官方網站自行查詢", 20)
            )
    return result("L3", list({s.id: s for s in signals}.values()), available=bool(ctx.text))


def verify_l4(ctx):
    signals = []
    leaks = [
        e
        for e in ctx.network_trace
        if e.observed and e.sensitive_data and not e.authorized_destination and not same_site(e.url, ctx.url)
    ]
    if sum(e.trigger in {"keyup", "input", "keydown"} for e in leaks) >= 3:
        signals.append(
            sig("keystroke_exfil", "觀測到至少三次敏感輸入隨鍵盤事件送往未授權的站外目的地", 100, True, True)
        )
    elif leaks:
        signals.append(
            sig("sensitive_external_transfer", "觀測到敏感資料送往未授權的站外目的地", 85, True, True)
        )
    if any(not same_site(a, ctx.url) for a in ctx.form_actions):
        signals.append(sig("external_form_action", "表單設定送往站外網址；尚未證明資料已外傳", 20))
    if any(re.search(r"\beval\s*\(|\bnew\s+Function\s*\(", s) for s in ctx.scripts):
        signals.append(sig("dynamic_code", "腳本包含動態程式碼執行，需要进一步檢查用途", 10))
    if any(
        e.observed and e.canary_detected and not e.authorized_destination and not same_site(e.url, ctx.url)
        for e in ctx.network_trace
    ):
        signals.append(sig("canary_exfil", "採集軌跡中的金絲雀標記流向未授權站外目的地", 100, True, True))
    return result("L4", signals, available=bool(ctx.trace_collected or ctx.form_actions or ctx.scripts))


def verify_l5(ctx):
    signals = []
    if ctx.domain_age_days is not None and ctx.domain_age_days < 30:
        signals.append(sig("young_domain", f"網域註冊僅 {ctx.domain_age_days} 天", 20, True))
    if ctx.tls_valid is False:
        signals.append(sig("invalid_tls", "TLS 憑證驗證失敗", 25, True))
    return result("L5", signals, available=ctx.domain_age_days is not None or ctx.tls_valid is not None)


def verify_l6(ctx):
    signals = []
    if len(ctx.probe_texts) >= 2:
        base = ctx.probe_texts[0][:10000]
        if any(
            SequenceMatcher(None, base, t[:10000], autojunk=True).ratio() < 0.45 for t in ctx.probe_texts[1:]
        ):
            signals.append(
                sig(
                    "probe_content_difference",
                    "不同探測身分收到差異較大的內容；也可能是 RWD、驗證頁或 A/B 測試",
                    15,
                )
            )
    return result("L6", signals, available=len(ctx.probe_texts) >= 2)


def verify_l7(ctx):
    return LayerResult(layer="L7", user_facing_reason="L7 需要 LLM 靜態程式碼審查；未執行 JavaScript")


def verify_l8(ctx):
    changed = (
        ctx.previous_sensitive_fields is not None
        and not ctx.previous_sensitive_fields
        and ctx.sensitive_fields
    )
    return result(
        "L8",
        [sig("new_sensitive_form", "與歷史快照相比，頁面新增敏感資料欄位", 25)] if changed else [],
        available=ctx.previous_sensitive_fields is not None,
    )


def verify_l9(ctx):
    hits = sum(word in ctx.text for word in ["登录", "银行卡", "身份证", "验证码", "网络"])
    return result(
        "L9",
        [sig("locale_inconsistency", "頁面混用不同地區的詞彙；僅作低權重輔助訊號", 5)] if hits >= 2 else [],
        available=bool(ctx.text),
    )


def verify_l10(ctx):
    # Pipeline supplements this with the locally reviewed fingerprint store.
    return LayerResult(layer="L10")


def verify_l11(ctx):
    return result(
        "L11",
        [sig("missing_business_pages", "採集資料指出缺少經營資訊頁面", 5)]
        if ctx.missing_business_pages
        else [],
        available=ctx.missing_business_pages is not None,
    )


def check_download(download: Download, page_url: str):
    signals = []
    name = unquote(download.filename).lower()
    if name.endswith((".apk", ".exe", ".scr", ".msi", ".lnk", ".js")):
        signals.append(sig("executable_download", "下載檔案可執行程式或安裝應用程式", 25, True))
    if "\u202e" in name or re.search(r"\.(?:pdf|jpg|docx?)\.(?:exe|scr|js|lnk)$", name):
        signals.append(sig("disguised_download", "檔名使用雙副檔名或方向控制字元掩飾類型", 45, True))
    if download.declared_type == "application/pdf" and download.magic_hex:
        try:
            if not bytes.fromhex(download.magic_hex).startswith(b"%PDF-"):
                signals.append(sig("download_type_mismatch", "宣稱 PDF，但檔案開頭不符合 PDF 格式", 35, True))
        except ValueError:
            signals.append(sig("invalid_magic_sample", "無法解析提供的檔案格式樣本", 0))
    if not download.user_initiated:
        signals.append(sig("automatic_download", "下載未由使用者主動點擊", 15, True))
    if not same_site(download.url, page_url):
        signals.append(sig("external_download", "下載來源與目前網站不同", 5))
    return signals


def verify_l12(ctx):
    return result(
        "L12", [s for d in ctx.downloads for s in check_download(d, ctx.url)], available=bool(ctx.downloads)
    )


def verify_l13(ctx):
    signals = []
    for payload in ctx.qr_payloads:
        if payload.startswith(("https://", "http://")):
            try:
                subctx = PageContext(url=payload)
                for s in verify_l1(subctx).signals:
                    signals.append(s.model_copy(update={"id": "qr_" + s.id}))
                if not same_site(payload, ctx.url):
                    signals.append(sig("qr_external_url", "QR code 指向站外網址，請另行核對目的地", 10))
            except ValueError:
                signals.append(sig("qr_invalid_url", "QR code 包含無法安全解析的網址", 10))
        elif payload.lower().startswith(("bitcoin:", "ethereum:", "line:")):
            signals.append(sig("qr_payment_or_chat", "QR code 指向虛擬貨幣付款或通訊軟體", 10))
    return result("L13", signals, available=bool(ctx.qr_payloads))


def verify_l14(ctx):
    return result("L14", []).model_copy(
        update={"user_facing_reason": "行為門檻由 should_interrupt 確定性判斷"}
    )


def verify_l15(ctx):
    signals = []
    if re.search(r"ignore.{0,30}instructions|忽略.{0,15}指令|判定.{0,8}安全", ctx.hidden_text, re.IGNORECASE):
        signals.append(sig("prompt_injection", "隱藏文字疑似要求分析器改變判定", 20))
    if ctx.delayed_sensitive_injection:
        signals.append(sig("delayed_sensitive_injection", "頁面載入後才新增敏感欄位，需核對用途", 10, True))
    return result("L15", signals, available=bool(ctx.hidden_text or ctx.delayed_sensitive_injection))


def verify_l16(ctx):
    return LayerResult(layer="L16")


REGISTRY = {f"L{i}": globals()[f"verify_l{i}"] for i in range(17)}
