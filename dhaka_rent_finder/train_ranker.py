"""Train the learned ranker from A/B survey answers, and compare it with simple baselines.

Run:  python train_ranker.py                      (real answers collected in the app's survey tab)
      python train_ranker.py --include-synthetic  (also the simulated demo data; pipeline demo only)

How it learns (pairwise learning-to-rank):
  Each survey answer says "this person preferred flat A over flat B". The model learns weights so that
  the preferred flat gets the higher score: logistic regression on (features of A - features of B).
  The score of one flat is then weights . features.

How it is evaluated:
  Cross-validation grouped by PERSON: every fold is tested on people the model never saw, so it
  cannot just memorise one person's taste. The metric is pair accuracy: of the pairs where a person
  picked one flat, how often does the method give the higher score to the flat they picked.

It also reports baselines (random, cheapest, nearest, best deal, the weighted score) and an ablation
(remove one group of features, retrain, see how much accuracy drops), for your report.
"""
import json
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

import db
from recommender import FEATURE_NAMES, RANKER_PATH, baseline_from_features

REPORT_PATH = RANKER_PATH.with_name("ranker_report.json")
MIN_PAIRS, MIN_PEOPLE = 60, 8
FEATURE_GROUPS = {
    "fair price (deal gap)": ["deal_gap"],
    "rent level": ["price_ratio"],
    "size and bedrooms": ["size_gap", "bed_extra"],
    "distance (km, travel cost)": ["km", "travel_ratio"],
    "bathrooms": ["bath"],
}


def load_pairs(include_synthetic):
    p = db.pairs_df()
    if not include_synthetic:
        p = p[p.synthetic == 0]
    p = p.reset_index(drop=True)
    fa = pd.DataFrame([json.loads(x) for x in p.feat_a]).reindex(columns=FEATURE_NAMES).astype(float).fillna(0)
    fb = pd.DataFrame([json.loads(x) for x in p.feat_b]).reindex(columns=FEATURE_NAMES).astype(float).fillna(0)
    ctx = pd.DataFrame([json.loads(x) for x in p.context])
    return p, fa, fb, ctx


def fit(fa, fb, y, cols):
    scale = np.maximum(pd.concat([fa[cols], fb[cols]]).std().values, 1e-6)
    d = (fa[cols].values - fb[cols].values) / scale
    model = LogisticRegression(fit_intercept=False, C=1.0, max_iter=1000)
    model.fit(np.vstack([d, -d]), np.concatenate([y, 1 - y]))   # mirrored copies remove any A/B position bias
    return model, scale


def margins(model, scale, fa, fb, cols):
    return model.decision_function((fa[cols].values - fb[cols].values) / scale)  # > 0 means A scores higher


def accuracy(margin, y):
    hit = np.where(margin == 0, 0.5, ((margin > 0) == (y == 1)).astype(float))   # a tie counts as half
    return float(hit.mean())


def cv_accuracy(cols, fa, fb, y, groups):
    marg = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=min(5, len(set(groups)))).split(fa, y, groups):
        m, sc = fit(fa.iloc[tr], fb.iloc[tr], y[tr], cols)
        marg[te] = margins(m, sc, fa.iloc[te], fb.iloc[te], cols)
    return accuracy(marg, y)


def main():
    include = "--include-synthetic" in sys.argv
    p, fa, fb, ctx = load_pairs(include)
    n, people = len(p), p.person_id.nunique()
    print(f"survey answers: {n} pairs from {people} people" + ("  [INCLUDES SIMULATED DEMO DATA]" if include else ""))
    if n < MIN_PAIRS or people < MIN_PEOPLE:
        sys.exit(f"Not enough survey data yet: need at least {MIN_PAIRS} pairs from {MIN_PEOPLE} different people. "
                 "The app keeps using the weighted score until then.")
    y = p.choice.values.astype(int)
    groups = p.person_id.values

    # ---- baselines on the same pairs
    cap = ctx.get("max_km", pd.Series([10.0] * n)).fillna(10.0).values
    uc = ctx.get("use_commute", pd.Series([True] * n)).fillna(True).astype(bool).values
    base_margin = baseline_from_features(fa.copy(), cap=cap, use_commute=uc).values - \
        baseline_from_features(fb.copy(), cap=cap, use_commute=uc).values
    methods = {
        "Random guess": 0.5,
        "Cheapest rent first": accuracy((fb.price_ratio - fa.price_ratio).values, y),
        "Nearest first": accuracy((fb.km - fa.km).values, y),
        "Best deal (below fair rent) first": accuracy((fa.deal_gap - fb.deal_gap).values, y),
        "Weighted score (default sliders)": accuracy(base_margin, y),
        "Learned pairwise ranker": cv_accuracy(FEATURE_NAMES, fa, fb, y, groups),
    }
    print("\nPair accuracy (higher is better; grouped cross-validation by person for the learned ranker)")
    for k, v in methods.items():
        print(f"  {k:36s} {v * 100:5.1f}%")

    # ---- ablation: drop one feature group at a time
    full = methods["Learned pairwise ranker"]
    ablation = {}
    for name, drop in FEATURE_GROUPS.items():
        keep = [f for f in FEATURE_NAMES if f not in drop]
        ablation[name] = cv_accuracy(keep, fa, fb, y, groups)
    print("\nAblation: accuracy when this group of features is removed (bigger drop = more important)")
    for k, v in ablation.items():
        print(f"  without {k:34s} {v * 100:5.1f}%   change {100 * (v - full):+5.1f} points")

    # ---- final model on everything
    model, scale = fit(fa, fb, y, FEATURE_NAMES)
    joblib.dump({"model": model, "scale": scale, "features": FEATURE_NAMES}, RANKER_PATH)
    weights = {f: round(float(w), 3) for f, w in zip(FEATURE_NAMES, model.coef_[0])}
    REPORT_PATH.write_text(json.dumps({
        "n_pairs": n, "n_people": int(people), "includes_synthetic": include,
        "pair_accuracy": {k: round(v, 4) for k, v in methods.items()},
        "ablation": {k: round(v, 4) for k, v in ablation.items()},
        "weights_per_std": weights}, indent=2))
    print("\nLearned weights (positive = people prefer more of it):", weights)
    print("Saved", RANKER_PATH)
    if include:
        print("NOTE: simulated people follow rules built from these same features, so these numbers only show "
              "that the pipeline works. Report accuracy only from real survey answers.")


if __name__ == "__main__":
    main()
