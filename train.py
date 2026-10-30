"""Train rent-prediction models, compare them honestly, and save artifacts.

Run:  python train.py

Two tests are reported for every model:
  random split    20% of listings held out at random. Flats from the same block appear on both sides,
                  so this is the optimistic number.
  block holdout   20% of whole blocks/buildings held out. The model must price places it has never
                  seen. This is the number to trust for new locations, and the best model is chosen on it.

Outputs
  models/rent_model.joblib   best model, refit on all data (for "what should this cost?")
  models/metrics.json        comparison tables
  data/listings_clean.csv    unique listings + out-of-fold `fair_rent` prediction
"""
import json
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from common import (CAT_COLS, DATA_CLEAN, FEATURES, METRICS_PATH, MODEL_PATH,
                    NUM_COLS, load_clean)

try:  # the diagram's XGBoost, used when installed
    from xgboost import XGBRegressor
except Exception:
    XGBRegressor = None

SEED = 42


def make_pre(scale=False):
    ohe = OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=10, sparse_output=False)
    num = StandardScaler() if scale else "passthrough"
    return ColumnTransformer([("cat", ohe, CAT_COLS), ("num", num, NUM_COLS)])


def build_models():
    models = {
        "Linear (Ridge)": Pipeline([("pre", make_pre(scale=True)), ("m", Ridge(alpha=3.0))]),
        "Random Forest": Pipeline([("pre", make_pre()),
                                   ("m", RandomForestRegressor(n_estimators=250, min_samples_leaf=2,
                                                               n_jobs=-1, random_state=SEED))]),
    }
    if XGBRegressor is not None:
        models["XGBoost"] = Pipeline([("pre", make_pre()),
                                      ("m", XGBRegressor(n_estimators=500, learning_rate=0.05, max_depth=6,
                                                         subsample=0.8, colsample_bytree=0.8, n_jobs=-1,
                                                         random_state=SEED))])
    else:  # same family of model (gradient boosted trees) from scikit-learn
        models["Gradient Boosting (sklearn)"] = Pipeline([
            ("pre", make_pre()),
            ("m", HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, max_leaf_nodes=31,
                                                random_state=SEED))])
    return models


def score(y_true_log, y_pred_log):
    y, p = np.expm1(y_true_log), np.expm1(y_pred_log)
    return {
        "MAE_BDT": round(float(mean_absolute_error(y, p))),
        "RMSE_BDT": round(float(np.sqrt(mean_squared_error(y, p)))),
        "R2_log": round(float(r2_score(y_true_log, y_pred_log)), 4),
        "MAPE_%": round(float(np.mean(np.abs(y - p) / y) * 100), 1),
        "within_20%": round(float(np.mean(np.abs(y - p) / y <= 0.20) * 100), 1),
    }


def evaluate(X, y, tr, te):
    out = {}
    for name, pipe in build_models().items():
        t = time.time()
        pipe.fit(X.iloc[tr], y.iloc[tr])
        out[name] = score(y.iloc[te], pipe.predict(X.iloc[te]))
        out[name]["train_seconds"] = round(time.time() - t, 1)
        print(f"  {name:30s}", out[name])
    return out


def main():
    df = load_clean(verbose=True)
    X, y = df[FEATURES], np.log1p(df["Price"])
    idx = np.arange(len(df))

    print("\nRandom split (optimistic: same blocks in train and test)")
    tr, te = train_test_split(idx, test_size=0.2, random_state=SEED)
    res_random = evaluate(X, y, tr, te)

    print("\nBlock holdout (honest: test blocks were never seen in training)")
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED).split(X, y, groups=df["Location"]))
    res_block = evaluate(X, y, tr, te)

    best = min(res_block, key=lambda k: res_block[k]["MAE_BDT"])
    print("\nBest model on the block holdout:", best)

    # Out-of-fold predictions: the "fair rent" of every listing comes from a model that
    # never saw that listing, so under/over-priced flats are not hidden by memorisation.
    # Grouped by block: a flat's fair rent never comes from a model that saw its own block, so it matches
    # what new flats get (the final model has not seen their listing either).
    oof = cross_val_predict(build_models()[best], X, y, cv=GroupKFold(n_splits=5), groups=df["Location"])
    df["fair_rent"] = np.expm1(oof).round(-2)
    DATA_CLEAN.parent.mkdir(exist_ok=True)
    df.to_csv(DATA_CLEAN, index=False)

    final = build_models()[best].fit(X, y)  # refit on everything for new inputs
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(final, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps({"best": best, "n_listings": len(df), "test_metrics": res_random,
                                        "block_holdout_metrics": res_block}, indent=2))
    print("Saved model, metrics and listings_clean.csv. Now run: python build_db.py")


if __name__ == "__main__":
    main()
