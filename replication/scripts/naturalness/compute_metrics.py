import pandas as pd

# Change these for your specific run:
TRAIN_SOURCE = "human_code"
TEST_SOURCE = "chatgpt_code"
ORDER = 6  # optional: include n-gram order
TOKENIZER = "llm"  # optional: include tokenizer

# Path to your output CSV
csv_file = f"python_kenLM_{TRAIN_SOURCE}_{ORDER}gram_{TOKENIZER}_no_comments.csv"
df = pd.read_csv(csv_file)

# Match only the correct test source (by label)
# (If your script outputs source as e.g., "human" not "human_code", map accordingly)
test_label = TEST_SOURCE.replace("_code", "")

df_tt = df[df["source"] == test_label]

print(f"\nTrain: {TRAIN_SOURCE}")
print(f"Test:  {TEST_SOURCE}")

means = df_tt[["cross_entropy_bits", "perplexity"]].mean()
stds  = df_tt[["cross_entropy_bits", "perplexity"]].std()

print("\nAverage cross-entropy and perplexity (all samples):")
print(means)

print("\nStd dev cross-entropy and perplexity (all samples):")
print(stds)