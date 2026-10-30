"""Tells you what is missing and which command to run next.  Run:  python check_setup.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGES = ["home", "find", "list_flat", "my_listing", "dashboard", "admin", "about"]


def main():
    steps, ok = [], True

    def need(path, how):
        nonlocal ok
        present = (ROOT / path).exists()
        print(f"[{'ok' if present else '--'}] {path}")
        if not present:
            ok = False
            steps.append(how)
        return present

    print("Pages")
    for p in PAGES:
        need(f"views/{p}.py", f"views/{p}.py is missing - re-extract the project zip")
    print("\nData and trained files")
    need("data/houserentdhaka.csv", "copy houserentdhaka.csv into the data folder (or: python make_sample_data.py for practice data)")
    need("data/landmarks.csv", "python fetch_landmarks.py   (needs internet)")
    need("data/listings_clean.csv", "python train.py")
    need("models/rent_model.joblib", "python train.py")
    need("data/rent.db", "python build_db.py --reset")
    print("\nPackages")
    for mod in ["pandas", "numpy", "sklearn", "joblib", "requests", "streamlit"]:
        try:
            __import__(mod)
            print(f"[ok] {mod}")
        except ImportError:
            ok = False
            print(f"[--] {mod}")
            steps.append("run setup.ps1 (or: python -m pip install -r requirements.txt)")
    print()
    if ok:
        print("Everything is in place. Start the site:  python -m streamlit run app.py")
    else:
        print("Next steps, in this order:")
        for i, s in enumerate(dict.fromkeys(steps), 1):
            print(f"  {i}. {s}")


if __name__ == "__main__":
    main()
