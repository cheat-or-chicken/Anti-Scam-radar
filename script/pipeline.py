import asyncio

from script.config import Settings
from script.investigation import investigate
from script.layers import REGISTRY
from script.layers.adjudication import adjudicate, should_interrupt, verify_l17
from script.layers.rules import gate, sig
from script.llm import LLM
from script.models import Analysis, LayerResult, PageContext, result
from script.storage import Store
from script.tools import VerificationTools


async def analyze(
    ctx: PageContext, settings: Settings | None = None, *, deep: bool = False, detectors: list | None = None
) -> Analysis:
    settings = settings or Settings()
    store = None
    audit_failed = False
    if settings.audit_enabled:
        try:
            store = Store(settings.database_path)
        except Exception:
            audit_failed = True
    llm = LLM(settings)
    tools = VerificationTools(settings, store)
    gate_value = gate(ctx)
    investigation_trace = []

    async def run(layer, verifier):
        try:
            return verifier(ctx)
        except Exception:
            return LayerResult(layer=layer, status="error", user_facing_reason="本層驗證失敗，其他層仍可執行")

    try:
        # Independent local layers always run, regardless of trust / L0 gate.
        layers = await asyncio.gather(*(run(name, fn) for name, fn in REGISTRY.items()))
        if store:
            try:
                matched = store.query_fingerprint_db(ctx.text)["matched"]
                layers[10] = result(
                    "L10",
                    [sig("reviewed_fingerprint", "頁面文字指紋符合人工複核的可疑樣本", 25)]
                    if matched
                    else [],
                )
                count = store.report_count(ctx.url)
                layers[16] = result(
                    "L16",
                    [sig("community_reports", "本網站有去重後的可疑回報，仍需獨立證據", min(20, count * 5))]
                    if count
                    else [],
                )
            except Exception:
                layers[10] = LayerResult(layer="L10", status="error")
                layers[16] = LayerResult(layer="L16", status="error")
        if deep and gate_value != "skip":
            investigation = await investigate(ctx, layers, llm, tools)
            investigation_trace = investigation["trace"]
            updates = {}
            for output in investigation["outputs"].values():
                if output.get("status") == "ok":
                    for key in ("domain_age_days", "scripts", "probe_texts"):
                        if key in output:
                            updates[key] = output[key]
            ctx = PageContext.model_validate({**ctx.model_dump(), **updates})
            for name in ("L4", "L5", "L6"):
                layers[int(name[1:])] = await run(name, REGISTRY[name])
        elif settings.network_enabled and gate_value != "skip" and ctx.domain_age_days is None:
            data = await tools.call("rdap_lookup", ctx)
            if data.get("status") == "ok":
                ctx = ctx.model_copy(update={"domain_age_days": data["domain_age_days"]})
                layers[5] = await run("L5", REGISTRY["L5"])
        if settings.llm_enabled and gate_value != "skip":
            # Reserve budget deterministically; fan out only the selected semantic tasks.
            priorities = ["L7", "L2", "L3", "L1", "L15", "L9"]
            selected = priorities[: max(0, settings.max_llm_calls - llm.calls)]
            from script.layers.code_review import verify_l7 as review_code

            replacements = await asyncio.gather(
                *(
                    review_code(ctx, llm) if n == "L7" else llm.supplement(layers[int(n[1:])], ctx)
                    for n in selected
                )
            )
            for name, replacement in zip(selected, replacements):
                layers[int(name[1:])] = replacement
        from script.blocklist import verify_blocklist

        layers.append(verify_blocklist(ctx))
        if detectors:
            from script.adaptive import detect

            hits = [hit for rule in detectors if (hit := detect(rule, ctx))]
            layers.append(result("ADAPTIVE", hits))
        decision = adjudicate(ctx, layers)
        layers.append(verify_l17(ctx, layers))
        analysis = Analysis(
            gate=gate_value,
            layers=layers,
            decision=decision,
            interrupted=should_interrupt(ctx.behavior, decision),
            llm_calls=llm.calls,
            investigation_trace=investigation_trace,
        )
        if store:
            try:
                analysis.audit_status = "saved"
                analysis.audit_id = store.record(ctx.url, analysis.model_dump())
            except Exception:
                audit_failed = True
        if audit_failed:
            analysis.audit_status = "error"
        return analysis
    finally:
        await llm.close()
