# Football Probability Lab

Free Streamlit dashboard for European football probability research and hypothetical parlay combinations.

## Run locally on a Mac

1. Install Python 3.11+ from https://www.python.org/downloads/.
2. Download and unzip this project.
3. Open Terminal in the project folder and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

4. Create a free API account at https://www.football-data.org/ and paste your token into the app sidebar. Optional bookmaker prices: https://the-odds-api.com/ (free-tier limitations).

## Free website hosting

1. Create a GitHub repository and upload `app.py`, `engine.py`, `requirements.txt` and this README.
2. Visit https://share.streamlit.io/ and deploy the repository's `app.py` using the free Community Cloud tier.
3. Store API keys as Streamlit secrets (recommended) or enter them in the sidebar each session. To use Streamlit secrets, create `.streamlit/secrets.toml` in the hosted app's secrets settings and use the environment-variable alternative below if configured. Never commit real tokens to GitHub.

### Optional secrets setup

For a deployed Streamlit app, add the following to the Streamlit Cloud app secrets interface:

```toml
FOOTBALL_DATA_TOKEN = "YOUR_TOKEN"
ODDS_API_KEY = "YOUR_OPTIONAL_KEY"
```

If you use Streamlit secrets, the app will pick them up from environment variables where supported; otherwise paste them into the sidebar.

## Limitations

- The free football-data.org tier may not provide all six competitions, and some endpoints are rate-limited.
- Only historical full-time goals feed the model. It does NOT account for injuries, xG, confirmed lineups, or market movement.
- The odds integration only attempts 1X2 and over 2.5 goals; team-name mismatches can prevent matches.
- Model probabilities are not validated or calibrated. They are exploratory estimates.
- Parlay probabilities assume independence across separate matches; shared contextual factors can still correlate outcomes.
- No automated background refresh or persistent prediction/result tracking is included in this first version. Streamlit refreshes on interaction and caches data for 30 minutes. A reliable daily job requires a separate scheduled workflow and data persistence.
- Do not use this tool to place bets automatically. Check local laws and age restrictions.
