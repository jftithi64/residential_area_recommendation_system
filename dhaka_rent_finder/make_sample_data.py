"""Make a SYNTHETIC practice dataset so the website can be tried without the real file.

Run:  python make_sample_data.py          (refuses to overwrite data/houserentdhaka.csv)
      python make_sample_data.py --force  (overwrite it)

The numbers are invented from simple rules (area price level x size x noise). They are NOT real rents. Use this only
to see the site working. For your report, put the real houserentdhaka.csv in data/ and run train.py on it.
"""
import sys

import numpy as np
import pandas as pd

from common import AREA_COORDS, DATA_RAW

PRICE_PER_SQFT = {"Gulshan": 52, "Banani": 48, "Baridhara": 55, "Baridhara DOHS": 50, "Banani DOHS": 45,
                  "Dhanmondi": 38, "Uttara": 27, "Bashundhara R-A": 30, "Mohammadpur": 24, "Mirpur": 20,
                  "Badda": 22, "Motijheel": 30, "Mohakhali": 34, "Mohakhali DOHS": 38, "Niketan": 40,
                  "Lalmatia": 33, "Shyamoli": 25, "Tejgaon": 28, "Eskaton": 34, "Malibagh": 25}
DEFAULT_PPSF = 22


def main():
    if DATA_RAW.exists() and "--force" not in sys.argv:
        sys.exit(f"{DATA_RAW} already exists; your real data is safe. Use --force to overwrite it.")
    rng = np.random.default_rng(1)
    areas = list(AREA_COORDS)
    rows = []
    for _ in range(4000):
        area = areas[int(rng.integers(len(areas)))]
        block = rng.choice(["Block A", "Block B", "Block C", "Block D", "Road 3", "Road 7", "Sector 4", ""])
        sqft = float(np.clip(rng.normal(1000, 380), 300, 3500))
        bed = int(np.clip(round(sqft / 380 + rng.normal(0, .4)), 1, 6))
        bath = int(np.clip(bed - int(rng.integers(0, 2)), 1, 5))
        ppsf = PRICE_PER_SQFT.get(area, DEFAULT_PPSF) * float(rng.lognormal(0, .18)) * (1 + .04 * (bath - 1))
        price = sqft * ppsf
        loc = f"{block}, {area}, Dhaka" if block else f"{area}, Dhaka"
        p = f"{price / 100000:.1f} Lakh" if price >= 100000 else f"{max(3, round(price / 1000))} Thousand"
        rows.append({"Location": loc, "Area": f"{int(sqft):,} sqft", "Price": p, "Bed": bed, "Bath": bath})
    df = pd.DataFrame(rows)
    df = pd.concat([df, df.sample(500, random_state=1)], ignore_index=True)   # real data has many repeats too
    DATA_RAW.parent.mkdir(exist_ok=True)
    df.to_csv(DATA_RAW)
    print(f"Wrote {len(df)} SYNTHETIC rows to {DATA_RAW}. Next: python train.py")


if __name__ == "__main__":
    main()
