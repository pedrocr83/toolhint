# Training Laya for disease-ontology classification

A runbook for standing up the ontology task on another machine and fine-tuning a
Laya checkpoint to do it well. Scope: **Laya only** — the Jev/SapBERT/scispaCy
comparison pieces are ignored here (scispaCy reappears once, only as a cheap
label generator).

Why fine-tune: base Laya checkpoints are general-English and weak on biomedical
text (they walked a glioblastoma abstract into "vulvar carcinoma"). Laya's own
numbers show fine-tuning lifts typed-decision accuracy from ~0.36 to ~0.77. The
plan is to teach Laya the MONDO branch decision on biomedical abstracts.

## 1. Machine setup

```bash
# clone/copy this project, then:
curl -LsSf https://astral.sh/uv/install.sh | sh      # if uv not installed
uv sync                                              # recreates the env from uv.lock
uv run python -c "from laya import Router; Router(preload=True)"   # warm base checkpoints
```

GPU strongly recommended for training (the repo's fine-tune notebook targets free
Kaggle 2×T4). Inference is fine on CPU (~33 ms/decision).

Bring these files from this repo: `jev_mondo.py` (the MONDO walk + OLS client +
`LayaDecider`), `pyproject.toml` + `uv.lock`, and — if you use the scispaCy
labeler — `bio_linker.py`.

## 2. The task, framed for Laya

Laya answers typed questions over a `state`. The ontology walk asks one `choice`
per MONDO layer (see `jev_mondo.py: choose_child`):

```
state    = {abstract, current_ontology_node}
question = {"child": {"type": "choice",
                      "criteria": {<MONDO child id>: <label>, ...}}}
label    = the correct child id for this abstract
```

So one training example = (abstract, candidate children at a node, correct
child). A full path down MONDO yields several examples (one per layer).

## 3. Build the training set (teacher-labeled)

You need labeled decisions. Cheapest path: auto-label a corpus of abstracts with
a grounded linker, then convert to per-layer choices.

1. Collect abstracts with a known disease focus (PubMed queries, or any corpus).
2. Ground each to a MONDO term with the scispaCy linker in `bio_linker.py`
   (`ScispacyLinker(...).link(abstract)` → MONDO id), or a strong LLM.
3. Walk MONDO from the root to that gold term (OLS `hierarchicalChildren`,
   already in `jev_mondo.py`); at each layer emit `(abstract, children, correct
   child on the gold path)`.
4. Hold out ~10–20% as a test split, stratified by top-level branch.

Aim for a few thousand decisions across varied disease areas (Laya's reference
set was ~2,000 across four workflows).

## 4. Fine-tune

Training code lives in the **Laya GitHub repo** (`NandhaKishorM/laya`), not the
pip package — use its fine-tune notebook
(`notebooks/laya_finetune_typed_decisions_*.ipynb`) and `research/` scripts. Steps
the notebook runs: build the dataset, train the decision heads, fit calibration
temperatures, evaluate, push to the Hub.

Two backbone options (verify the notebook exposes the encoder as a config field —
a Laya checkpoint is `{cfg["encoder"], head_layers, calibration}`, so it is
encoder-agnostic in principle):

- **Fine-tune the shipped checkpoint** (ModernBERT backbone). Simplest; general
  backbone caps biomedical accuracy.
- **Train on a biomedical backbone** — set the encoder to a biomedical model
  (`microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext`, or SapBERT
  `cambridgeltl/SapBERT-from-PubMedBERT-fulltext`) and train the heads on your
  dataset. Best expected accuracy for this domain. The shipped heads do **not**
  transfer to a new backbone — you retrain them.

Context budget: BiomedBERT/SapBERT = 512 tokens (fine for abstracts). Keep
`state` compact.

## 5. Evaluate

Point `LayaDecider` at your new checkpoint and run the existing walk on the test
split:

```bash
export LAYA_MODEL=<your-checkpoint-or-hf-id>
uv run jev_mondo.py laya
```

Score exact-match of the final MONDO term (and per-layer choice accuracy) against
the held-out gold. Compare fine-tuned vs base to confirm the lift.

## Checklist

- [ ] `uv sync` reproduces the env; base Laya loads
- [ ] corpus of abstracts collected
- [ ] teacher labels each abstract to a MONDO term
- [ ] per-layer `(abstract, children, correct child)` examples emitted; train/test split
- [ ] fine-tune in the Laya repo notebook (pick backbone)
- [ ] evaluate fine-tuned vs base on the test split
