"""
MoveInSync Play Store ratings dashboard (Streamlit).

Run locally:   streamlit run dashboard.py
Data source:   ratings.db (built by ratings_pipeline.py) or, if missing, reviews.csv (classified on load).
Deploy:        push the repo to GitHub, then create an app on share.streamlit.io pointing at dashboard.py.
"""
import os, sqlite3
import pandas as pd
import streamlit as st
from ratings_pipeline import classify

st.set_page_config(page_title="MoveInSync Play Store ratings", layout="wide")
st.title("MoveInSync employee app: Play Store ratings")

@st.cache_data(ttl=3600)
def load():
    if os.path.exists("ratings.db"):
        df = pd.read_sql("SELECT * FROM reviews", sqlite3.connect("ratings.db"), parse_dates=["at"])
    elif os.path.exists("reviews.csv"):
        df = pd.read_csv("reviews.csv")
        df["at"] = pd.to_datetime(df["at"])
        df["category"] = df["content"].fillna("").apply(classify)
        df["replied"] = df["replyContent"].notna().astype(int)
    else:
        return pd.DataFrame()
    df["month"] = df["at"].dt.to_period("M").dt.to_timestamp()
    return df

@st.cache_data(ttl=3600)
def store_listing():
    try:
        from google_play_scraper import app
        a = app("com.moveinsync.ets", lang="en", country="in")
        return a["score"], a["ratings"], a["histogram"]
    except Exception:
        return 4.64, 114872, None  # last known values (read 9 Oct 2026) if the live lookup fails

df = load()
if df.empty:
    st.error("No data found. Run `python ratings_pipeline.py --csv reviews.csv` or place reviews.csv next to this file.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    lo, hi = df["at"].min().date(), df["at"].max().date()
    default_lo = max(lo, (df["at"].max() - pd.DateOffset(months=24)).date())
    start, end = st.date_input("Review date range", (default_lo, hi), min_value=lo, max_value=hi)
    min_n = st.slider("Minimum reviews per app version", 20, 200, 50, 10)
    neg_alert = st.slider("Alert when negative share is above", 0.20, 0.60, 0.35, 0.01)

d = df[(df["at"].dt.date >= start) & (df["at"].dt.date <= end)]
neg = d[d["score"] <= 2]

score, n_ratings, hist = store_listing()
c = st.columns(5)
c[0].metric("Store headline", f"{score:.2f}" if score else "n/a", f"{n_ratings:,} ratings" if n_ratings else None, delta_color="off")
c[1].metric("Review average (range)", f"{d['score'].mean():.2f}", f"{len(d):,} reviews", delta_color="off")
c[2].metric("1 and 2 star share", f"{len(neg) / max(len(d), 1):.0%}")
c[3].metric("Reply rate, 1-2 star", f"{neg['replied'].mean():.0%}" if len(neg) else "n/a")
last30 = d[d["at"] > d["at"].max() - pd.Timedelta(days=30)]
prev30 = d[(d["at"] <= d["at"].max() - pd.Timedelta(days=30)) & (d["at"] > d["at"].max() - pd.Timedelta(days=60))]
c[4].metric("Last 30 days avg", f"{last30['score'].mean():.2f}", f"{last30['score'].mean() - prev30['score'].mean():+.2f} vs previous 30", )

st.subheader("Monthly average rating")
m = d.groupby("month")["score"].mean().rename("average rating")
st.line_chart(m)

left, right = st.columns(2)
with left:
    st.subheader("What drives 1 and 2 star reviews")
    specific = neg[neg["category"] != "Generic / no detail"]
    share = (specific["category"].value_counts() / max(len(specific), 1) * 100).round(1)
    st.bar_chart(share, horizontal=True)
    st.caption(f"{len(specific):,} specific negative reviews; {len(neg) - len(specific):,} give no detail. "
               "Keyword classifier, about 79% accurate on a hand-checked sample: directional only.")
with right:
    st.subheader("Negative reviews by category, per month")
    pick = st.multiselect("Categories", sorted(specific["category"].unique()),
                          default=[x for x in ["Login, logout & OTP", "Crashes, speed & stability", "Tracking, ETA & routing"] if x in set(specific["category"])])
    t = specific[specific["category"].isin(pick)].groupby(["month", "category"]).size().unstack(fill_value=0)
    st.bar_chart(t)

st.subheader("Versions: negative share (release regressions)")
g = d.groupby("reviewCreatedVersion")["score"].agg(reviews="count", avg_rating="mean", negative_share=lambda s: (s <= 2).mean())
g = g[g["reviews"] >= min_n].sort_values("reviews", ascending=False).round(2)
g["alert"] = g["negative_share"] > neg_alert
st.dataframe(g, width='stretch')

st.subheader("Developer reply rate by month")
st.line_chart(d.groupby("month")["replied"].mean().rename("reply rate"))

st.subheader("Most upvoted negative reviews")
top = neg.sort_values("thumbsUpCount", ascending=False).head(15)[["at", "score", "reviewCreatedVersion", "thumbsUpCount", "category", "content"]]
st.dataframe(top, width='stretch')
