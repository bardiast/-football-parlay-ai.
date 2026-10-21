# Football Probability Lab — Database Edition

Retains the Pro Experience UI and the existing three football data sources. Adds private Supabase email/password accounts, row-level-secured cloud prediction tracking, settlement on app visits, saved parlays and match watchlists.

## Setup
1. In Supabase **SQL Editor**, paste and run `supabase_schema.sql` once.
2. In Supabase **Authentication → Providers → Email**, ensure email login is enabled. Email confirmation may be required.
3. In Streamlit Cloud → app settings → Secrets, set `SUPABASE_URL` and `SUPABASE_KEY` (publishable key only). Never use or commit a Supabase secret key.
4. Upload the package's Python files and requirements.txt to your existing GitHub app repository (and keep SQL file for reference).
5. Open the app, sign up or sign in using the Cloud storage section in the sidebar.

## Important limitations
- No background worker: predictions are captured and results are settled when a signed-in user opens or refreshes the app.
- Only results present in the football-data.org historical response can settle; older records may remain pending.
- First pre-kickoff prediction per user, fixture and market is kept (duplicates ignored). No odds-change snapshots or advanced fuzzy odds matching yet.
- Sign-in tokens are held in Streamlit session state and may expire; sign in again if needed.
- Cloud accounts are private per user via PostgreSQL Row Level Security.
- Parlay probabilities remain uncalibrated and independence-based.
