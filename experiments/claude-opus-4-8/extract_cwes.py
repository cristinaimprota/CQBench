"""Extract per-author CWE distributions for the 600-task subset from the raw
Semgrep result files, using the benchmark's own loader (legacy.load_raw_vulnerabilities
+ cwes_from_raw). Config paths are rewritten from the export ROOT to the parent repo
where the actual risultati_*/C_security data lives."""
import dataclasses, json, collections, os
from pathlib import Path

os.chdir("/home/cristina01/humanAIcodesmells/CQBench-v1-export")
import cqbench.legacy as L

m = L.rq4_module()
EXPORT = m.ROOT
PARENT = EXPORT.parent

def remap(p):
    if isinstance(p, Path):
        try:
            return PARENT / p.relative_to(EXPORT)
        except ValueError:
            return p
    if isinstance(p, dict):
        return {k: remap(v) for k, v in p.items()}
    return p

# rewrite every config so paths resolve in the parent repo
for lang, cfg in list(m.LANGUAGE_CONFIGS.items()):
    changes = {}
    for f in dataclasses.fields(cfg):
        v = getattr(cfg, f.name)
        if isinstance(v, (Path, dict)):
            changes[f.name] = remap(v)
    m.LANGUAGE_CONFIGS[lang] = dataclasses.replace(cfg, **changes)

# subset source_ids by language
B = Path("/tmp/claude-1002/-home-cristina01-humanAIcodesmells/4bdfd546-2b10-4bda-baec-95e09396810c/scratchpad/bench")
tasks = [json.loads(l) for l in open(B / "subset_tasks.jsonl")]
by_lang = collections.defaultdict(list)
for t in tasks:
    by_lang[t["language"]].append(t["source_id"])

AUTHORS = {"python": ("human", "chatgpt", "dsc", "qwen"),
           "java":   ("human", "chatgpt", "dsc", "qwen"),
           "c":      ("human", "gptoss", "dsc", "qwen")}
# unify chatgpt(py/java)+gptoss(c) -> "openai"
def norm_author(lang, a):
    if a == "chatgpt" or a == "gptoss":
        return "openai"
    return a

# author -> Counter(cwe), and author -> set of (lang,key) with >=1 vuln
cwe_counts = collections.defaultdict(collections.Counter)
vuln_tasks = collections.defaultdict(int)
total_tasks = collections.defaultdict(int)
percwe_lang = collections.defaultdict(lambda: collections.Counter())

for lang, keys in by_lang.items():
    authors = AUTHORS[lang]
    raw = L.load_raw_vulnerabilities(lang, authors, keys)
    for a in authors:
        na = norm_author(lang, a)
        for key in keys:
            total_tasks[na] += 1
            rec = raw.get((a, key))
            cwes = L.cwes_from_raw(rec) if rec else set()
            if cwes:
                vuln_tasks[na] += 1
            for c in cwes:
                cwe_counts[na][c] += 1
                percwe_lang[(na, lang)][c] += 1

# add Claude from results.jsonl (already has semgrep cwes)
claude = [json.loads(l) for l in open(B / "results.jsonl")]
for r in claude:
    total_tasks["claude"] += 1
    cs = r.get("cwes") or []
    if cs:
        vuln_tasks["claude"] += 1
    for c in cs:
        cwe_counts["claude"][c] += 1
        percwe_lang[("claude", r["language"])][c] += 1

order = ["claude", "human", "openai", "dsc", "qwen"]
allcwes = collections.Counter()
for a in order:
    allcwes.update(cwe_counts[a])
top = [c for c, _ in allcwes.most_common(14)]

print("=== vulnerability incidence (tasks with >=1 CWE finding / 600) ===")
for a in order:
    print(f"  {a:8s} {vuln_tasks[a]}/{total_tasks[a]} = {vuln_tasks[a]/total_tasks[a]:.3f}")
print()
print("=== CWE finding counts per author (top CWEs across subset) ===")
print(f"{'CWE':10s}" + "".join(f"{a:>9s}" for a in order))
for c in top:
    print(f"{c:10s}" + "".join(f"{cwe_counts[a][c]:9d}" for a in order))
print()

# save CSV
with open(B / "cwe_distribution.csv", "w") as f:
    f.write("scope,author,cwe,count\n")
    for a in order:
        for c, n in sorted(cwe_counts[a].items()):
            f.write(f"ALL,{a},{c},{n}\n")
    for (a, lang), ctr in percwe_lang.items():
        for c, n in sorted(ctr.items()):
            f.write(f"{lang},{a},{c},{n}\n")
print("wrote cwe_distribution.csv")
