# Dhaka House Rent Finder

## Quick start in VS Code (Windows)
1. **File > Open Folder...** and choose this folder. Accept the "install recommended extensions" prompt.
2. Open a terminal (Ctrl+`) and run `powershell -ExecutionPolicy Bypass -File setup.ps1`. It creates `.venv` and
   installs the packages. Then Ctrl+Shift+P > "Python: Select Interpreter" > the one in `.venv`.
3. **Data:** copy your `houserentdhaka.csv` into the `data` folder.
   No file yet? Run `python make_sample_data.py` to make SYNTHETIC practice data (not real rents).
4. Open `.env` and set your own `RENT_ADMIN_PASSWORD`.
5. Press **F5** and run these from the Run and Debug dropdown, one after another (wait for each to finish):
   `3. Train rent model` > `4. Build database (reset)` > `1. Run website (Streamlit)`.
   Optional but recommended (needs internet): `2. Fetch Dhaka landmarks` first, then build the database again,
   to load every school, college, university, office and area of Dhaka.
6. Open http://localhost:8501.
Run `python check_setup.py` any time to see what is missing. Tests: `python -m unittest discover -s tests -v`.

Same steps in a terminal:
```
python make_sample_data.py     # only if you have no real data file
python fetch_landmarks.py      # optional, internet
python train.py
python build_db.py --reset
python -m streamlit run app.py
```

A website where a renter enters a rent budget and picks a school, college, university or office; the system
measures road distance on a map, estimates a fair rent for every flat with machine learning, adds up the real
monthly cost, and ranks specific flats. Owners can list flats, an admin reviews them, and a dashboard shows
how many flats are listed in each area and which areas need fresher information.

## Run it (Windows)
```
python -m pip install --only-binary :all: pandas numpy scikit-learn joblib requests
python -m pip install --only-binary :all: streamlit
python -m streamlit run app.py
```
`--only-binary :all:` stops pip from trying to compile packages. Open http://localhost:8501.
The trained model and the database are already included. To rebuild them:
```
python train.py          # clean data, train and compare rent models (random split AND block holdout)
python fetch_landmarks.py   # once, needs internet: all schools, colleges, universities, offices and areas of Dhaka
python build_db.py       # create / refresh data/rent.db (keeps owner listings; add --reset to start over)
```
Admin password: the Admin page stays locked until you set your own (`admin123` and `change-me` are refused).
Put it in the `.env` file (`RENT_ADMIN_PASSWORD=...`) or, in PowerShell:
```
$env:RENT_ADMIN_PASSWORD = "your-password"
python -m streamlit run app.py
```

## The pages
| Page | For | What it does |
|---|---|---|
| Home | everyone | live numbers, what to do next |
| Find a flat | renters | filters, ranked flats, compare, map, A/B survey, fair-rent calculator |
| List a flat | owners, tenants | add a flat for rent, or share the rent you pay; gets a private edit code |
| Manage my listing | owners | change rent, confirm still available, mark rented, remove (listing number + edit code) |
| Dashboard | everyone | flats per area, areas needing updates, rent spread, owner activity, model accuracy |
| Admin | admin | review new entries, change status, run the upkeep job, import rows |
| About and privacy | everyone | how it works, accuracy, limits, privacy |

## Life of a listing
`pending` (just submitted) -> `approved` (appears in search) -> `rented`, `expired` (not confirmed for 45 days)
or `removed`. Entries can also be `rejected`. Entries with a rent more than 40% away from the model's fair rent
are flagged for a closer look. Only approved flats that are available for rent are recommended. "Rent I pay"
entries are never recommended; they are used to test and improve the price model. Owner entries are NOT used to
train the rent model unless you choose to retrain, so they act as a true test set.

## Automatic upkeep
`python maintenance.py` does everything below (the Admin page has a button for the same job):
1. imports new rows from a form export (`data/form_responses.csv`, or the web address in the `FORM_CSV_URL`
   environment variable, e.g. a Google Sheet published as CSV); new rows wait for review
2. finds exact map positions for flats that have an address
3. hides flats not confirmed for 45 days
4. tests the rent model on approved owner-listed flats and logs the error (shown on the Dashboard)

Run it every night on Windows (change the folder if yours differs):
```
schtasks /Create /SC DAILY /TN "RentUpkeep" /ST 02:00 /TR "cmd /c cd /d E:\house_rent_system && python maintenance.py"
```
A person still approves new entries; that is what keeps fake rows out.

### Google Form setup
Make a Google Form whose question titles are exactly these column names (or rename the header row of the response
sheet): `location` (e.g. "Block C, Mirpur 10, Mirpur, Dhaka"), `sqft`, `bed`, `bath`, `price`, `tenant_rule`
(family / bachelor_male / bachelor_female / any), `floor`, `lift`, `gas`, `parking`, `generator`, `furnished`
(1 or 0), `available_from`, `source_url`, `address`. Publish the response sheet as CSV and set `FORM_CSV_URL`.

## Files
| Layer | Files |
|---|---|
| Website | `app.py` (router), `views/*.py` (pages), `ui.py` |
| Logic | `recommender.py`, `listing_logic.py`, `coverage.py`, `maintenance.py` |
| Map | `maps.py` (OpenStreetMap OSRM free, or Google Routes API with your key) |
| Practice data | `make_sample_data.py` (synthetic rows so you can try the site; never use for the report) |
| ML | `train.py` (rent model), `train_ranker.py` (learned ranker), `seed_demo_survey.py` (demo only) |
| Database | `db.py`, `build_db.py`, `data/rent.db`; `import_extra_listings.py`, `geocode_places.py` |
| Places | `fetch_landmarks.py` (OpenStreetMap -> landmarks.csv), `nearby.py` (nearby areas for the List a flat page) |
| Tests | `tests/test_core.py` - run `python -m unittest discover -s tests -v` |

## Map options
OpenStreetMap is the default: free, no key, public demo server with fair-use limits, driving distance, times ignore
traffic. Google Maps: paste your key under "Distance source" on the Find page; it needs a Google Cloud project with
the Routes API enabled. Google lists 10,000 free calls per month per billable item but does not say whether a billing
account is required, so check its current terms. The Google path is tested against a simulated reply only.

## Survey and learned ranker
Ask classmates to answer 15-20 pairs each on the Find page ("Help improve" tab), then run `python train_ranker.py`.
It prints baselines (random, cheapest, nearest, best deal, weighted score) and an ablation. Demo without real people
(SIMULATED data, proves the pipeline only): `python seed_demo_survey.py` then `python train_ranker.py --include-synthetic`.

## Before putting it on the internet
- SQLite is a file. Free hosting (e.g. Streamlit Community Cloud) wipes files on restart, so everything people add
  would be lost. Use a hosted database (e.g. Postgres) for a real deployment. On your own computer SQLite is fine.
- Contact details are personal data: keep the consent box and the privacy page, and collect only what you need.
- Set a strong RENT_ADMIN_PASSWORD (the Admin page refuses weak ones).

## Honest limits (for your report)
- The original data has no address, floor, facilities, tenant rule or contact; rents are asking prices.
- 47% of raw rows were exact duplicates; merged (28,800 -> 15,242 unique).
- Rent model error is about 13% on a random split but about 16-17% on blocks it has never seen.
- Dataset flats are located at block or area level. Flats with an exact position use it.
- Travel cost and advance are assumptions. OpenStreetMap times ignore traffic.
- Simulated survey data is circular; only real survey answers give a real accuracy figure.
- Map data (c) OpenStreetMap contributors (ODbL).

## Demo addresses (read this before your report)
Off by default. `python build_db.py --demo-addresses` gives every dataset row a made-up placeholder address such as "Flat 4B, House 27, Road 5, Mirpur, Dhaka"
(`make_demo_addresses.py`, deterministic). They are NOT real, are always shown as "[demo address]", and set no map
position, so distances are still measured from the block. Say in your report that they are synthetic.
Remove them: `python make_demo_addresses.py --remove`.
Real addresses come only from flats that owners add on the "List a flat" page.

## What each page does now
- **Find a flat:** budget, bedrooms, destination (school, college, university, office or any area), tenant type,
  advanced weights and cost assumptions; ranked cards with total monthly cost, map, side-by-side compare,
  fair-rent calculator with an error range, and the A/B survey.
- **List a flat:** pick area and block, see nearby areas and landmarks (with optional road distance), then the details.
  Gets a listing number and a private edit code.
- **Manage my listing:** change rent, confirm still available, mark rented, remove, contact visibility; locks after
  5 wrong codes.
- **Dashboard / Admin / About:** coverage by area, rent spread, model accuracy; review queue, status changes,
  upkeep job, CSV import (admin password required); how it works and privacy.

## Changes in this version
- Unknown distance no longer counts as 0 km (it is scored as the farthest known distance).
- Fair rent uses block-grouped out-of-fold predictions; dataset flat ids are now stable across retrains
  (run `python train.py` and `python build_db.py --reset` once; old survey answers refer to the old ids).
- "Fair rent" is described as typical asking rent. Dataset rows are scraped asking prices, not confirmed availability.
- No meaningful minimum rent when listing (only typing-error guards: at least 1,000 per month). Remove any minimum-rent slider in views/find.py.
- Database: connections are closed, schema runs once, WAL mode, indexes, atomic id for new listings.
- Edit codes: 10 random bytes, salted PBKDF2 hash (old plain hashes still work).
- Admin: set RENT_ADMIN_PASSWORD; views/admin.py should refuse to start with the default `admin123`.
