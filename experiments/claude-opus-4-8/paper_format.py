"""Reproduce the paper's result format (Table 4 structural, Fig.6 ODC, Table 5
defect stats, Fig.8 CWE heatmap) for the 600-task subset, adding Claude as a
fifth author alongside Human / OpenAI GPT / DeepSeek / Qwen."""
import json, csv, collections, os, statistics
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

B = Path("/tmp/claude-1002/-home-cristina01-humanAIcodesmells/4bdfd546-2b10-4bda-baec-95e09396810c/scratchpad/bench")
OUT = Path("/home/cristina01/humanAIcodesmells/CQBench-v1-export/runs/claude-opus-4-8/paper_figures")
OUT.mkdir(parents=True, exist_ok=True)

AUTH_FILES = {"Human": B/"baselines/human.jsonl", "OpenAI GPT": B/"baselines/openai.jsonl",
              "DeepSeek": B/"baselines/dsc.jsonl", "Qwen": B/"baselines/qwen.jsonl",
              "Claude": B/"results.jsonl"}
AUTHORS = list(AUTH_FILES)
LANGS = ["python", "java", "c"]
data = {a: [json.loads(l) for l in open(p)] for a, p in AUTH_FILES.items()}

# ---------- Table 4: structural complexity (mean +/- std over strict-nontrivial) ----------
CX = [("nloc_mean","NLOC"),("ccn_mean","CCN"),("parameter_count_mean","PC"),
      ("max_nesting_depth_mean","MND"),("halstead_volume_mean","V"),
      ("halstead_difficulty_mean","D"),("maintainability_index_mean","MI")]
def cx_vals(rows, lang, key):
    out=[]
    for r in rows:
        if r["language"]!=lang or not r.get("strict_nontrivial"): continue
        v=(r.get("complexity") or {}).get(key)
        if isinstance(v,(int,float)): out.append(float(v))
    return out

t4=[]
for lang in LANGS:
    for a in AUTHORS:
        row={"Language":lang,"Author":a}
        for key,lbl in CX:
            vs=cx_vals(data[a],lang,key)
            row[lbl]=(statistics.mean(vs), statistics.pstdev(vs)) if vs else (float("nan"),0)
        t4.append(row)
with open(OUT/"table4_structural.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["Language","Author"]+[l for _,l in CX])
    for r in t4: w.writerow([r["Language"],r["Author"]]+[f"{r[l][0]:.2f}±{r[l][1]:.2f}" for _,l in CX])

# ---------- ODC defects (Fig.6 proportions + Table 5 stats) ----------
ODC=[("def_assignment","Assignment"),("def_algorithm","Algorithm"),("def_interface","Interface"),
     ("def_checking","Checking"),("def_timing","Timing/Serialization"),("def_function_class_object","Function/Class/Object")]
def odc_totals(rows, lang):
    tot=collections.Counter()
    for r in rows:
        if r["language"]!=lang: continue
        for col,lbl in ODC: tot[lbl]+=int(r.get(col) or 0)
    return tot
def defect_stats(rows, lang):
    sel=[r for r in rows if r["language"]==lang]
    defective=sum((r.get("defects_total") or 0)>0 for r in sel)
    vuln=sum((r.get("vulns_total") or 0)>0 for r in sel)
    total=sum(int(r.get("defects_total") or 0) for r in sel)
    return len(sel), defective, vuln, total
with open(OUT/"table5_defect_stats.csv","w",newline="") as f:
    w=csv.writer(f); w.writerow(["Language","Author","N","Defective Samples","Defective %","Vulnerable Samples","Vulnerable %","Total Defects"])
    for lang in LANGS:
        for a in AUTHORS:
            n,dfc,vln,tot=defect_stats(data[a],lang)
            w.writerow([lang,a,n,dfc,f"{100*dfc/n:.1f}",vln,f"{100*vln/n:.1f}",tot])

# ---------- CWE counts from cwe_distribution.csv ----------
cwe=collections.defaultdict(lambda: collections.defaultdict(collections.Counter))  # lang->author->cwe
namemap={"claude":"Claude","human":"Human","openai":"OpenAI GPT","dsc":"DeepSeek","qwen":"Qwen"}
for row in csv.DictReader(open(B/"cwe_distribution.csv")):
    if row["scope"] in LANGS:
        cwe[row["scope"]][namemap[row["author"]]][row["cwe"]]+=int(row["count"])

# ================= FIGURES =================
# Exact palette extracted from the paper's figures (vector fills).
# ODC categories, in order: Assignment, Algorithm, Interface, Checking,
# Timing/Serialization, Function/Class/Object.
COLORS=["#008080","#40e0d0","#afeeee","#4169e1","#87cefa","#4682b4"]  # teal->blue
HEATMAP_CMAP="Blues"  # paper CWE heatmap uses a blue sequential map
plt.rcParams.update({"font.size":9,"figure.dpi":140})

# Fig 6: ODC proportion stacked horizontal bars, one subplot per language
fig,axes=plt.subplots(1,3,figsize=(13,3.4))
for ax,lang in zip(axes,LANGS):
    labels=[l for _,l in ODC]
    yauth=AUTHORS[::-1]
    left=np.zeros(len(yauth))
    props={a:odc_totals(data[a],lang) for a in yauth}
    totals={a:sum(props[a].values()) or 1 for a in yauth}
    for ci,lab in enumerate(labels):
        vals=np.array([props[a][lab]/totals[a] for a in yauth])
        ax.barh(yauth,vals,left=left,color=COLORS[ci],label=lab,edgecolor="white",linewidth=0.5)
        left+=vals
    ax.set_xlim(0,1); ax.set_title({"python":"(a) Python","java":"(b) Java","c":"(c) C"}[lang])
    ax.set_xlabel("Proportion of total defects")
    ax.xaxis.set_major_formatter(lambda x,_:f"{int(x*100)}%")
handles,labs=axes[0].get_legend_handles_labels()
fig.legend(handles,labs,loc="lower center",ncol=6,frameon=False,bbox_to_anchor=(0.5,-0.08))
fig.suptitle("Distribution of ODC defect types across authors (600-task subset)",y=1.02)
fig.tight_layout(); fig.savefig(OUT/"fig_odc_defect_distribution.png",bbox_inches="tight"); plt.close(fig)

# Fig 8: CWE heatmap per language (authors x top-10 CWE by total)
fig,axes=plt.subplots(1,3,figsize=(13,4.6))
for ax,lang in zip(axes,LANGS):
    tot=collections.Counter()
    for a in AUTHORS:
        for c,n in cwe[lang][a].items(): tot[c]+=n
    top=[c for c,_ in tot.most_common(10)]
    M=np.array([[cwe[lang][a].get(c,0) for a in AUTHORS] for c in top])
    im=ax.imshow(M,cmap=HEATMAP_CMAP,aspect="auto")
    ax.set_xticks(range(len(AUTHORS))); ax.set_xticklabels(AUTHORS,rotation=40,ha="right")
    ax.set_yticks(range(len(top))); ax.set_yticklabels(top)
    ax.set_title({"python":"(a) Python","java":"(b) Java","c":"(c) C"}[lang])
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j,i,str(M[i,j]),ha="center",va="center",
                    fontsize=7,color="white" if M[i,j]>M.max()*0.55 else "black")
fig.suptitle("Top CWE finding counts by author (600-task subset)",y=1.02)
fig.tight_layout(); fig.savefig(OUT/"fig_cwe_heatmap.png",bbox_inches="tight"); plt.close(fig)

# Structural grouped-bar figure (NLOC, CCN, V per language) to visualize Table 4
fig,axes=plt.subplots(1,3,figsize=(13,3.6))
metrics=[("nloc_mean","NLOC"),("ccn_mean","CCN"),("halstead_volume_mean","Halstead V")]
x=np.arange(len(LANGS)); w=0.16
# authors coloured from the paper's teal->blue palette; Claude = royalblue to stand out
acolors={"Human":"#008080","OpenAI GPT":"#40e0d0","DeepSeek":"#87cefa","Qwen":"#4682b4","Claude":"#4169e1"}
for ax,(key,lbl) in zip(axes,metrics):
    for k,a in enumerate(AUTHORS):
        vals=[statistics.mean(cx_vals(data[a],lang,key) or [0]) for lang in LANGS]
        ax.bar(x+(k-2)*w,vals,w,label=a,color=acolors[a])
    ax.set_xticks(x); ax.set_xticklabels([l.capitalize() for l in LANGS]); ax.set_title(lbl)
axes[0].set_ylabel("mean (strict-nontrivial)")
handles,labs=axes[0].get_legend_handles_labels()
fig.legend(handles,labs,loc="lower center",ncol=5,frameon=False,bbox_to_anchor=(0.5,-0.06))
fig.suptitle("Structural complexity by author and language (600-task subset)",y=1.02)
fig.tight_layout(); fig.savefig(OUT/"fig_structural_complexity.png",bbox_inches="tight"); plt.close(fig)

# ---- print tables for chat ----
print("TABLE 4 — structural complexity (mean; strict-nontrivial; 600-subset)")
print(f"{'lang':7s}{'author':11s}"+"".join(f"{l:>9s}" for _,l in CX))
for r in t4:
    print(f"{r['Language']:7s}{r['Author']:11s}"+"".join(f"{r[l][0]:9.2f}" for _,l in CX))
print("\nTABLE 5 — defect/vuln stats (600-subset; n=200/lang)")
print(f"{'lang':7s}{'author':11s}{'defectiv%':>10s}{'vuln%':>7s}{'totDef':>8s}")
for lang in LANGS:
    for a in AUTHORS:
        n,dfc,vln,tot=defect_stats(data[a],lang)
        print(f"{lang:7s}{a:11s}{100*dfc/n:10.1f}{100*vln/n:7.1f}{tot:8d}")
print("\nFigures written to", OUT)
for p in sorted(OUT.glob("*.png")): print("  ",p.name)
