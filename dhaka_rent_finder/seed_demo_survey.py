"""DEMO ONLY: fill the survey table with SIMULATED students so the learned ranker can be shown.

Run:  python seed_demo_survey.py
      python train_ranker.py --include-synthetic

These are not real people. Each simulated student has a hidden budget, destination and taste
(how much they care about price, a good deal, the right size, and how far they will travel). Their
A/B choices come from those hidden rules plus random noise, and are stored with synthetic=1.
Because the hidden rules use the same features the ranker sees, accuracy on this data is flattering:
it proves the pipeline works, nothing more. Real accuracy needs the real survey.
"""
import numpy as np

import db
import recommender

rng = np.random.default_rng(7)
N_PEOPLE, PAIRS_EACH = 80, 20


def main():
    lm = db.load_landmarks()
    n = 0
    for i in range(N_PEOPLE):
        dest = lm.iloc[int(rng.integers(len(lm)))]
        budget = float(rng.choice([10000, 12000, 15000, 20000, 25000, 35000]))
        beds = int(rng.choice([1, 2, 2, 3]))
        max_km = 15.0
        pool = recommender.prepare(budget, min_bed=beds, max_bed=beds + 1,
                                   destination={"name": dest["name"], "lat": dest["lat"], "lon": dest["lon"]},
                                   max_km=max_km, use_network=False)
        if len(pool) < 30:
            continue
        care_price, care_deal, care_size = rng.uniform(0.2, 1.0, 3)
        tol = float(rng.uniform(3, 12))   # km this person is happy to travel
        ctx = {"budget_max": budget, "max_km": max_km, "use_commute": True}
        for _ in range(PAIRS_EACH):
            a, b = pool.iloc[rng.choice(len(pool), 2, replace=False)].to_dict("records")

            def utility(r):
                return (-2.0 * care_price * r["f_price_ratio"] + 3.0 * care_deal * np.clip(r["f_deal_gap"], -.3, .3)
                        - 2.0 * care_size * r["f_size_gap"] - 1.5 * max(0.0, (r["f_km"] - tol) / tol)
                        - 0.05 * r["f_km"] + 0.2 * (r["f_bath"] >= 2))
            p_a = 1 / (1 + np.exp(-(utility(a) - utility(b)) / 0.4))
            fa = {k: (0.0 if np.isnan(a["f_" + k]) else float(a["f_" + k])) for k in recommender.FEATURE_NAMES}
            fb = {k: (0.0 if np.isnan(b["f_" + k]) else float(b["f_" + k])) for k in recommender.FEATURE_NAMES}
            db.add_pair(f"sim_{i:03d}", dest["name"], a["listing_id"], b["listing_id"], int(rng.random() < p_a),
                        fa, fb, ctx, synthetic=1)
            n += 1
    print(f"Added {n} simulated survey answers (synthetic=1).")


if __name__ == "__main__":
    main()
