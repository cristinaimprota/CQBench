import sys
import os
import pylcs
import numpy as np
from crystal_bleu import *

def edit_dist(hyp, ref):
	tmp = pylcs.edit_distance(hyp, ref)
	res_norm = 1-(tmp/max(len(hyp),len(ref)))
	return res_norm
 
def calc_ED(hyps, refs):
	scores = [edit_dist(h, r) for h, r in zip(hyps, refs)]
	mean_ed = np.mean(scores)
	min_ed = np.min(scores)
	max_ed = np.max(scores)
	median_ed = np.median(scores)
	q1_ed = np.percentile(scores, 25)
	q3_ed = np.percentile(scores, 75)
	stdev_ed = np.std(scores)
	formatted_score = (f'ED: {mean_ed * 100:.2f}% (min: {min_ed:.3f}, max: {max_ed:.3f}, median: {median_ed:.3f}, Q1: {q1_ed:.3f}, Q3: {q3_ed:.3f}, stdev: {stdev_ed:.3f})')
	print(formatted_score)
	return formatted_score

def calc_EM(hyps, refs):
	scores = []
	for hyp, ref in zip(hyps, refs):
		hyp_tokens = hyp.split()
		ref_tokens = ref.split()
		if hyp_tokens == ref_tokens:
			scores.append(1)
		else:
			scores.append(0)
	mean_em = np.mean(scores)
	stdev_em = np.std(scores)
	formatted_score=f"EM: {mean_em * 100:.2f}% (stdev: {stdev_em:.3f})"
	print(formatted_score)
	return formatted_score

def calc_crystalBLEU(hyps, refs, re_compute_ngrams: bool, language: str = "python"):
	cache_folder = "crystal_cache"
	os.makedirs(cache_folder, exist_ok=True)

	if re_compute_ngrams:
		cache_files = [
			os.path.join(cache_folder, "python_trivially_shared_ngrams.pickle"),
			os.path.join(cache_folder, "python_trivially_shared_ngrams.txt"),
		]
		deleted_any = False
		for cache_file in cache_files:
			if os.path.exists(cache_file):
				os.remove(cache_file)
				deleted_any = True
		if deleted_any:
			print("ngrams files deleted. Will compute trivially shared ngrams")
		else:
			print("No files to delete. Will compute trivially shared ngrams")
	else:
		print("Loading trivially shared ngrams")

	trivial_ngrams = compute_trivially_shared_ngrams(refs, language, cache_folder)
	scores = compute_crystal_bleu(refs, hyps, trivial_ngrams, language)
	mean_crystal = np.mean(scores)
	min_crystal = np.min(scores)
	max_crystal = np.max(scores)
	median_crystal = np.median(scores)
	stdev_crystal = np.std(scores)
	q1_crystal = np.percentile(scores, 25)
	q3_crystal = np.percentile(scores, 75)
	formatted_score = (f'\nCrystalBLEU: {mean_crystal * 100:.2f}% (min: {min_crystal:.3f}, max: {max_crystal:.3f}, median: {median_crystal:.3f}, Q1: {q1_crystal:.3f}, Q3: {q3_crystal:.3f}, stdev: {stdev_crystal:.3f})')
	print(formatted_score)
	return formatted_score


def read_json_singlefile(filename):
	hyps = []
	refs = []

	with open(filename, 'r') as hyps_f:
		data = json.load(hyps_f)
		hyps = [pred['prediction'] for pred in data]
	with open(filename, 'r') as refs_f:
		data = json.load(refs_f) 
		refs = [ref['reference'] for ref in data]
	return hyps, refs


def read_jsonl_singlefile(filename, model_name):
	hyps = []
	refs = []

	print(f"Model name: {model_name}")

	with open(filename, 'r') as file:
		for line in file:
			data = json.loads(line)
			refs.append(data.get("human_code"))
			hyps.append(data.get(model_name))

	return hyps, refs
		

if __name__ == '__main__':
	"""
		Read with the correct function to parse input file
	"""

	total_hyps = []
	total_refs = []
	
	for model_name in ["chatgpt_code", "dsc_code", "qwen_code"]:
		total_hyps, total_refs = read_jsonl_singlefile('./java_dataset_dsc_qwen_FINAL.jsonl', model_name)	# Filename containing both predictions and references

		print(f"Number of predictions: {len(total_hyps)}")
		print(f"Number of references: {len(total_refs)}")


		# for i in range(0, 10):
		# 	print(f"Prediction: {total_hyps[i]}\n")
		# 	print(f"Reference: {total_refs[i]}\n")
		
		calc_crystalBLEU(total_hyps, total_refs, True, "java")		
		# calc_ED(total_hyps, total_refs)
