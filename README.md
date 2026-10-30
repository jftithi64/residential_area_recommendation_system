# Dhaka House Rent Finder

## Quick start in VS Code (Windows)
1. **File > Open Folder...** and choose this folder. Accept the "install recommended extensions" prompt.
2. Open a terminal (Ctrl+`) and run `powershell -ExecutionPolicy Bypass -File setup.ps1`. It creates `.venv` and
   installs the packages. Then Ctrl+Shift+P > "Python: Select Interpreter" > the one in `.venv`.
3. **Data:** copy your `houserentdhaka.csv` into the `data` folder.
   No file yet? Run `python make_sample_data.py` to make SYNTHETIC practice data (not real rents).
4. Open `.env` and set `ADMIN_EMAIL` and `ADMIN_PASSWORD` (see Admin below).
5. Press **F5** and run these from the Run and Debug dropdown, one after another (wait for each to finish):
   `3. Train rent model` > `4. Build database (reset)` > `1. Run website (Streamlit)`.
   Optional but recommended (needs internet): `2. Fetch Dhaka landmarks` first, then build the database again,
   to load every school, college, university, office and area of Dhaka.
6. Open http://localhost:8501.
**Vehicles and fares:** in *Find a flat > Advanced* the renter picks a vehicle (bus, metro, rickshaw, CNG, ride-share bike or car,
own motorbike, walk, or custom). The fare of every flat is then calculated from its distance: `fare = max(minimum fare,
starting fare + km x rate per km)`, times round trips per month. The rates are editable on the page; the starting values
are in `transport.py` (`DEFAULT_MODES`). They are estimates, not official tariffs.

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
Forgot password: on the **Log in** page, press **Forgot password?**, enter your email, then type the 6-digit code from the email and a new password.
It uses the same `SMTP_USER` / `SMTP_PASS` settings as sign-up. (Admin passwords are changed in `.env`, not by email.)

Admin: put `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env` (8+ characters, letters and numbers; `admin123` and `change-me`
are refused). When the site starts, that admin account is created automatically. The admin logs in on the normal
**Log in** page with that email and password, and an **Admin** page appears in the menu (only admins see it). Change the
password in `.env` and restart to change it. More admins: they sign up, then `python make_admin.py their@email`.

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
- Give admin rights only to accounts you trust (`python make_admin.py`).

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
  upkeep job, CSV import (admin accounts only); how it works and privacy.

## Changes in this version
- Unknown distance no longer counts as 0 km (it is scored as the farthest known distance).
- Fair rent uses block-grouped out-of-fold predictions; dataset flat ids are now stable across retrains
  (run `python train.py` and `python build_db.py --reset` once; old survey answers refer to the old ids).
- "Fair rent" is described as typical asking rent. Dataset rows are scraped asking prices, not confirmed availability.
- No meaningful minimum rent when listing (only typing-error guards: at least 1,000 per month). Remove any minimum-rent slider in views/find.py.
- Database: connections are closed, schema runs once, WAL mode, indexes, atomic id for new listings.
- Edit codes: 10 random bytes, salted PBKDF2 hash (old plain hashes still work).
- Admin: role-based (make_admin.py); no shared password.

## Pictures (assets/)
All artwork is original SVG drawn for this project, so there are no licence problems. `logo.svg` (sidebar),
`hero_skyline.svg` (banner), `flat_placeholder_0-2.svg` (flats without a photo), `feat_*.svg` and `illus_*.svg`
(home page), `favicon.png` (browser tab). `ui.asset_uri()` loads them; a missing file is skipped, never an error.
Owner photos still replace the placeholder automatically once uploaded.


## Menu rights (role-wise page access)

Admins get a **Menu rights** page (menu, or My account > Menu rights). It shows a table of pages against account
types (Renter, Owner / landlord). Tick a box to give that type the page; press **Save rights**. **Reset to default**
allows every page again.

- Hidden pages disappear from the menu and are also blocked if reached another way (`permissions.guard`).
- Administrators always see everything. Home, About and My account are always on.
- Visitors (people who are not logged in) have their own column. By default a visitor gets Home, Browse flats,
  Is my rent fair? and About; List a flat, Add photos, Manage my listing, Advanced search and Dashboard need an account.
  Those pages stay in the visitor's menu with a lock and open a "Log in or sign up" prompt. Log in and Sign up are the
  first items of a visitor's menu and also buttons on Home. For renters and owners a switched-off page is hidden.
- Saved in table `role_permissions` (created automatically). A role change by `make_admin.py` applies at once.
- To make a new page configurable: add it to `PAGES` in `permissions.py` and call `permissions.guard("key")`
  near the top of the page file.

## Adding real data for areas with no rents (collect_data.py)

The 55 areas added to the lists have no flats in the dataset yet. Real rents must come from real adverts, surveys or
visits. `collect_data.py` checks what people collect and stores it:

1. `python collect_data.py template` writes `data/collected_template.csv`. One row per real flat: area, road,
   house_no, flat, sqft, bed, bath, rent_bdt, source_type (advert / survey / broker / visit), source_url, date_seen.
2. `python collect_data.py check my_rows.csv` lists every problem with its line number and changes nothing.
3. `python collect_data.py add my_rows.csv --train` stores the good rows in `data/collected_real.csv`, then retrains the
   model and rebuilds the database. Without `--train`, run `python train.py` and `python build_db.py` yourself.
4. `python collect_data.py status` shows each area against the target of 20 (also saved as `data/area_progress.csv`).

Rows are refused when the area is not in the list, road or house is missing, the rent per sqft is not believable, the
advert has no link, the date is in the future or older than a year, or any field holds a phone number or email.
Repeats are skipped. Stored rows keep their road and house and are marked `real_collected` (never `synthetic_demo`).
Two flats with the same road, size, rooms and rent count as one when the model trains.


## Sign-up interests and the Insights page

- **Interests.** The sign-up form has an optional "Your interests" part: what brings the person here, areas, bedrooms and
  highest rent. It is stored in table `user_interests` (created automatically) and can be edited on My account.
- **Insights (admin only).** Menu > Insights shows people signed up (per day, total over time, renters and owners, verified
  and active), flats listed by people (per day, by status, by area), the review queue (waiting, oldest, turned down) and
  the interests, including areas people want next to the live owner flats there. Flats are not tied to an account, so the
  number of different owners who listed cannot be shown.
