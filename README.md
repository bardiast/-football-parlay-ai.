# Football Probability Lab — Watchlist UI Fix

This is the Supabase Edition with visible **☆ Watchlist** buttons on Discover and Match Analysis cards, plus a **Save this match to watchlist** action at the top of Match Analysis. The saved watchlist panel on Discover is expanded by default.

## Deploy
Replace the existing repository files with the files in this ZIP, then commit. Your existing Supabase SQL schema and Streamlit Secrets remain unchanged.

## Verify
Sign in, press ☆ Watchlist on a match card, then open the expanded Saved match watchlist panel on Discover. Refresh the app and confirm the match is still listed. Remove it to test deletion.

Watchlist buttons only appear while signed in. Saving requires the Supabase watchlist table and correct RLS policies.
