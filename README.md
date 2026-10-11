# MoveInSync Play Store ratings: diagnosis and repeatable pipeline

Forward Deployed Engineer case study. **Full report:** `<paste your Claude Doc link here>`
**Live dashboard:** `<paste your Streamlit link here>`
**Author:** `<your name, email>`

## The question
MoveInSync's Play Store ratings should be higher. Why are they where they are, what should be fixed, and in what order? And because "How are our ratings?" will keep being asked, how do we answer it every week without redoing the analysis?

## Headline findings (details and evidence in the report)
- Store headline is **4.64** (114,872 ratings, vs Routematic 4.34), but written reviews average **3.75** over the last 24 months.
- Unhappy users write, happy users stay silent: 92% of 1-2 star raters left a review vs 13% of 5-star raters.
- Three problems account for two thirds of specific complaints: **stability (24%)**, **live tracking and ETA (21%)**, **login, logout and OTP (21%)**. About 66% of specific complaints are app-fixable defects.
- Login complaints arrive in waves tied to releases (Jan-Feb 2025 on v11.5.17, Jun-Jul 2025, Oct 2025).
- Developer replies went from about 98% of reviews to about 2% in mid-2024.

## What is in this repo
| File | Purpose |
|---|---|
| `scrape_moveinsync.py` | One-off pull of app facts (all MoveInSync apps and a competitor) and all reviews of the employee app. Writes `reviews.csv`. |
| `scrape_workplace.py` | Finds other MoveInSync apps by name and pulls their reviews. |
| `ratings_pipeline.py` | Repeatable pipeline: fetch only new reviews, classify them into 10 journey stages, store in SQLite, print a weekly summary with surge and version alerts. |
| `dashboard.py` | Streamlit dashboard on top of the data. |
| `reviews.csv` | The 24,314 public reviews used in the report (scraped 9 Oct 2026). |

## Run it
```bash
pip install -r requirements.txt

# 1. Load data (use the included CSV, or fetch live reviews with no flag)
python ratings_pipeline.py --csv reviews.csv      # first load
python ratings_pipeline.py                        # daily: fetches only new reviews, prints weekly summary
python ratings_pipeline.py --report-only --days 7 # summary only

# 2. Dashboard
streamlit run dashboard.py
```

**Schedule it:** run `python ratings_pipeline.py` daily with cron or a GitHub Action, and post the printed summary to Slack or email for Product, Engineering, Operations and Support. The summary flags categories that doubled versus the previous period and any app version whose 1-2 star share passes 35%.

**Deploy the dashboard:** push this repo to GitHub, then create an app at share.streamlit.io with `dashboard.py` as the entry point.

## Method and limitations
- Classification is a keyword scorer (English plus common Hinglish terms), not an LLM. It matched a manual reading of 55 of 70 fresh negative reviews (79%), so category shares are directional. To use an LLM, replace `classify()` in `ratings_pipeline.py` with a call that returns one category name.
- Review text overstates dissatisfaction (see the 92% vs 13% finding), and each review gets one primary category.
- Reviews show symptoms, not causes. Root causes need checking against crash logs, OTP delivery data and release notes.
- Full limitations are in the report.

## Tools
google-play-scraper, Python, pandas, SQLite, Streamlit, and Claude (AI assistant) for coding, review reading and drafting.
