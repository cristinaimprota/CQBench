import json, collections, os
B=os.environ['B']
ODC=[("def_assignment","Assignment"),("def_algorithm","Algorithm"),("def_interface","Interface"),
     ("def_checking","Checking"),("def_timing","Timing/Serial"),("def_function_class_object","Func/Class/Obj")]
authors={
 "claude": B+"/results.jsonl",
 "human":  B+"/baselines/human.jsonl",
 "openai": B+"/baselines/openai.jsonl",
 "dsc":    B+"/baselines/dsc.jsonl",
 "qwen":   B+"/baselines/qwen.jsonl",
}
data={a:[json.loads(l) for l in open(p)] for a,p in authors.items()}
# check cwe availability
for a,rows in data.items():
    ncwe=sum(len(r.get("cwes") or []) for r in rows)
    # only report once
print("CWE tokens present per author:", {a:sum(len(r.get('cwes') or []) for r in data[a]) for a in authors})
print()

def incidence(rows, col, lang=None):
    sel=[r for r in rows if lang is None or r["language"]==lang]
    if not sel: return None
    return sum((r.get(col) or 0)>0 for r in sel)/len(sel)

for scope in ["ALL","python","java","c"]:
    lang=None if scope=="ALL" else scope
    print(f"===== ODC defect-type incidence  ({scope}) — fraction of tasks with >=1 finding =====")
    hdr="author   " + " ".join(f"{lbl:>13s}" for _,lbl in ODC) + f"{'anyDefect':>11s}{'anyVuln':>9s}"
    print(hdr)
    for a in ["claude","human","openai","dsc","qwen"]:
        vals=[incidence(data[a],col,lang) for col,_ in ODC]
        anyd=incidence(data[a],"defects_total",lang)
        anyv=incidence(data[a],"vulns_total",lang)
        print(f"{a:8s} "+" ".join(f"{v:13.2f}" for v in vals)+f"{anyd:11.2f}{anyv:9.2f}")
    print()

# Claude's own CWE distribution (baselines have none)
cwes=collections.Counter()
for r in data["claude"]:
    for c in (r.get("cwes") or []): cwes[c]+=1
print("Claude top CWEs (count of tasks-findings):", dict(cwes.most_common(12)))
