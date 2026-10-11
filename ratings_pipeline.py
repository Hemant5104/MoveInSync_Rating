"""
MoveInSync Play Store ratings pipeline: pull new reviews -> classify -> store -> weekly summary.

Setup:    pip install google-play-scraper pandas
Daily:    python ratings_pipeline.py                 (fetches new reviews from Google Play)
Offline:  python ratings_pipeline.py --csv reviews.csv   (loads an existing scrape)
Report:   python ratings_pipeline.py --report-only

Schedule it with cron or a daily GitHub Action, then send the printed summary to Slack or email.
To use an LLM instead of keyword rules, replace classify() with a call that returns one category name.
"""
import argparse, re, sqlite3
import pandas as pd

APP = "com.moveinsync.ets"
DB = "ratings.db"
SPIKE_NEG_SHARE = 0.35   # alert when a version's 1-2 star share passes this
MIN_VERSION_N = 40

CATS = {
 'Login, logout & OTP': r"logs? ?out|logged out|logouts?|logging out|signing out|login|log in|logging in|re-?login|sign[- ]?in|\botps?\b|verification code|password|session|register",
 'Booking & scheduling': r"\bbook|roster|schedul|\bshift|slot|address|preference|trip history|previous trips?|upcoming trips?|seat|autopopulat|office (name|location)|boarding points?",
 'Tracking, ETA & routing': r"track|gps|live location|vehicle location|route|routing|\bmaps?\b|navigation|\beta\b|pick-?up|pick up|drop|clubbing|pooling|sequence|detour|nodal|shuttle|arriv|late\b|on time|not assign|allocat|timing",
 'No-show & cancellation': r"no[- ]?show|cut ?off|cancel|wait ?list|waitlist|penalt|buffer time",
 'Crashes, speed & stability': r"crash|slow|\blag|loading|buffering|not working|doesn.?t work|does not work|won.?t open|not (getting )?open|unable to (open|access)|stuck|freez|blank|error|\bbugg?y?\b|hang|glitch|not installed|uninstall|reinstall|stopped working|technical issue|empty response|update",
 'Support & grievance': r"support|customer (care|service|executive)|helpline|help ?desk|ivr|no response|complaint|grievance|admin|unprofessional|calling (feature|button)|can.?t call|cannot call",
 'Driver, vehicle & ops': r"driver|vendor|vehicle|fleet|rude|abusive|logistics|dispatcher|service provider",
 'UI/UX & notifications': r"\bui\b|\bux\b|interface|user[- ]friendly|confus|notification|pop ?up|disclaimer|design|skip rating",
 'Permissions & privacy': r"permission|microphone|privacy|suspicious|shady",
 'Safety': r"\bsos\b|safety|security|\bguard|panic|women|female|harass",
}
ORDER = list(CATS)

def classify(text):
    t = str(text).lower()
    sc = {c: len(re.findall(p, t)) for c, p in CATS.items()}
    best = max(sc.values())
    return 'Generic / no detail' if best == 0 else next(c for c in ORDER if sc[c] == best)

def fetch_new(conn):
    from google_play_scraper import reviews, Sort
    last = pd.read_sql("SELECT MAX(at) m FROM reviews", conn)['m'][0]
    last = pd.to_datetime(last) if last else pd.Timestamp('2000-01-01')
    out, token = [], None
    while True:
        batch, token = reviews(APP, lang='en', country='in', sort=Sort.NEWEST, count=200, continuation_token=token)
        out += batch
        if not batch or pd.to_datetime(batch[-1]['at']) <= last or token is None:
            break
    return pd.DataFrame(out)

def store(conn, df):
    df = df.copy()
    df['at'] = pd.to_datetime(df['at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    df['category'] = df['content'].fillna('').apply(classify)
    df['replied'] = df['replyContent'].notna().astype(int)
    keep = ['reviewId', 'at', 'score', 'thumbsUpCount', 'reviewCreatedVersion', 'content', 'category', 'replied']
    df[keep].to_sql('staging', conn, if_exists='replace', index=False)
    conn.execute("INSERT OR IGNORE INTO reviews SELECT * FROM staging")
    conn.commit()

def summary(conn, days=7):
    df = pd.read_sql("SELECT * FROM reviews", conn, parse_dates=['at'])
    end = df['at'].max()
    cur = df[df['at'] > end - pd.Timedelta(days=days)]
    prev = df[(df['at'] <= end - pd.Timedelta(days=days)) & (df['at'] > end - pd.Timedelta(days=2 * days))]
    neg = cur[cur.score <= 2]
    print(f"=== Ratings summary, {days} days to {end:%Y-%m-%d} ===")
    print(f"Reviews: {len(cur)} (prev {len(prev)}) | avg {cur.score.mean():.2f} (prev {prev.score.mean():.2f}) | "
          f"1-2 star share {len(neg)/max(len(cur),1):.0%} | reply rate on 1-2 star {neg.replied.mean() if len(neg) else 0:.0%}")
    print("\nTop complaint categories this period:")
    print((neg.category.value_counts().head(5)).to_string())
    pc = prev[prev.score <= 2].category.value_counts()
    surging = [(c, n, pc.get(c, 0)) for c, n in neg.category.value_counts().items() if n >= 3 and n >= 2 * max(pc.get(c, 0), 1)]
    if surging:
        print("\nSURGING vs previous period:", ", ".join(f"{c} ({n} vs {p})" for c, n, p in surging))
    v = cur.groupby('reviewCreatedVersion').score.agg(['count', lambda s: (s <= 2).mean()])
    v.columns = ['n', 'neg_share']
    flagged = v[(v.n >= MIN_VERSION_N) & (v.neg_share > SPIKE_NEG_SHARE)]
    if len(flagged):
        print("\nALERT versions above the negative-share threshold:\n" + flagged.round(2).to_string())

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv'); ap.add_argument('--report-only', action='store_true'); ap.add_argument('--days', type=int, default=7)
    a = ap.parse_args()
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS reviews(reviewId TEXT PRIMARY KEY, at TEXT, score INT, thumbsUpCount INT,
                    reviewCreatedVersion TEXT, content TEXT, category TEXT, replied INT)""")
    if not a.report_only:
        store(conn, pd.read_csv(a.csv) if a.csv else fetch_new(conn))
    summary(conn, a.days)
