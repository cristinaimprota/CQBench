"""Pick representative Claude generations that triggered defects / CWEs, and
reproduce the exact findings with the benchmark's own analyzers."""
import json, os
from pathlib import Path
os.chdir("/home/cristina01/humanAIcodesmells/CQBench-v1-export")
from cqbench.analyzers import analyze_defects, analyze_semgrep
from cqbench.config import ROOT

B = Path("/tmp/claude-1002/-home-cristina01-humanAIcodesmells/4bdfd546-2b10-4bda-baec-95e09396810c/scratchpad/bench")
RULES = ROOT / "cqbench/rules/semgrep.json"
results = {json.loads(l)["task_id"]: json.loads(l) for l in open(B/"results.jsonl")}
code = {json.loads(l)["task_id"]: json.loads(l)["code"] for l in open(B/"predictions.jsonl")}
tasks = {json.loads(l)["task_id"]: json.loads(l) for l in open(B/"subset_tasks.jsonl")}

def pick(lang, want_cwe=None, want_defect=False, maxlen=1500):
    cands=[]
    for tid,r in results.items():
        if r["language"]!=lang: continue
        if want_cwe and want_cwe not in (r.get("cwes") or []): continue
        if want_defect and (r.get("defects_total") or 0)==0: continue
        cands.append(tid)
    # shortest code first for readable snippets
    cands.sort(key=lambda t: len(code[t]))
    for tid in cands:
        if len(code[tid])<=maxlen:
            return tid
    return cands[0] if cands else None

# (language, want_cwe, want_defect, note)
targets=[
 ("python", "CWE-89",  False, "SQL injection"),
 ("python", None,      True,  "defect (pylint/ODC)"),
 ("java",   None,      True,  "defect (PMD/ODC)"),
 ("c",      "CWE-120", False, "buffer overflow"),
 ("c",      "CWE-78",  False, "OS command injection"),
]
chosen=[]
seen=set()
for lang,cwe,dfct,note in targets:
    tid=pick(lang,cwe,dfct)
    if tid and tid not in seen:
        seen.add(tid); chosen.append((tid,note))

out=["# Example Claude generations with defects / CWEs\n",
     "Snippets from `predictions.jsonl`; findings reproduced with the benchmark's own",
     "analyzers (pylint/PMD/clang-tidy + Semgrep with the vendored rules).\n"]
for tid,note in chosen:
    r=results[tid]; t=tasks[tid]; c=code[tid]
    dv=analyze_defects(r["language"], c)
    vv=analyze_semgrep(c, r["language"], RULES)
    print("="*80); print(f"{tid}  [{note}]  sig={t['signature']['text']}")
    out.append(f"\n## `{tid}` — {note}\n")
    out.append(f"**Task:** `{t['signature']['text']}` ({r['language']}, stratum {r['stratum']})\n")
    out.append("```"+{"python":"python","java":"java","c":"c"}[r["language"]])
    snip=c if len(c)<=1600 else c[:1600]+"\n/* …truncated… */"
    out.append(snip); out.append("```\n")
    # defects
    defs=dv.get("defect_findings",[])[:4]
    if defs:
        out.append("**Defects (ODC):**")
        for f in defs:
            sym=f.get("symbol") or f.get("rule") or f.get("check")
            line=f.get("line") or f.get("beginline")
            msg=(f.get("message") or f.get("description") or "").strip().replace("\n"," ")[:140]
            out.append(f"- `{sym}` → ODC {f.get('odc_category')} (line {line}): {msg}")
        print(f"  defects_total={dv['defects_total']} shown={len(defs)}")
    # vulns
    vulns=vv.get("vulnerability_findings",[])[:4]
    if vulns:
        out.append("\n**Vulnerabilities (CWE):**")
        for f in vulns:
            ex=f.get("extra",{}); md=ex.get("metadata",{})
            cwe=md.get("cwe"); cwe=cwe if isinstance(cwe,str) else (cwe[0] if cwe else "")
            line=(f.get("start") or {}).get("line")
            rule=f.get("check_id","").split(".")[-1]
            msg=(ex.get("message") or "").strip().replace("\n"," ")[:160]
            sev=ex.get("severity","")
            out.append(f"- {cwe} `{rule}` [{sev}] (line {line}): {msg}")
        print(f"  vulns_total={vv['vulns_total']} cwes={vv['cwes']}")
    out.append("")

Path(B/"EXAMPLES.md").write_text("\n".join(out), encoding="utf-8")
dest=Path("/home/cristina01/humanAIcodesmells/CQBench-v1-export/runs/claude-opus-4-8/EXAMPLES_defects_cwes.md")
dest.write_text("\n".join(out), encoding="utf-8")
print("\nwrote EXAMPLES to", dest)
