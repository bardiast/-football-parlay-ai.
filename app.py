import os, datetime as dt
import pandas as pd
import streamlit as st
from engine import LEAGUES, fixtures_and_history, odds_lookup, candidates, build_parlays

st.set_page_config(page_title='Football Probability Lab',page_icon='⚽',layout='wide')
st.title('⚽ Football Probability Lab')
st.caption('Free research dashboard • Six European competitions • Probabilities are model estimates, not guarantees')
with st.sidebar:
    st.header('Data connections')
    football_key=st.text_input('football-data.org API token',value=os.getenv('FOOTBALL_DATA_TOKEN',''),type='password',help='Free registration: football-data.org')
    odds_key=st.text_input('The Odds API key (optional)',value=os.getenv('ODDS_API_KEY',''),type='password',help='Free usage limits apply; market coverage varies')
    days=st.slider('Upcoming days',1,7,3)
    st.info('Odds are optional. Without verified prices, the app does not claim any selection has positive expected value.')
    st.caption('On free API plans, some competitions may be unavailable or rate-limited.')

@st.cache_data(ttl=1800,show_spinner=False)
def load_fixtures(token,days):return fixtures_and_history(token,days)
@st.cache_data(ttl=1800,show_spinner=False)
def load_odds(token):return odds_lookup(token)
if not football_key:
    st.warning('Enter a football-data.org API token in the sidebar to load actual matches. No fabricated fixtures or odds are shown.')
    st.markdown('**Start here:** Create a free account at football-data.org, copy your API token, paste it in the sidebar, and refresh.')
    st.stop()
with st.spinner('Loading match history and upcoming fixtures…'):
    fixtures,history,warnings=load_fixtures(football_key,days)
if warnings:st.warning('Data provider notes: '+warnings)
a,b,c=st.columns(3)
a.metric('Upcoming fixtures',len(fixtures));b.metric('Completed matches in sample',len(history));c.metric('Competitions requested',len(LEAGUES))
if not fixtures:
    st.info('No upcoming fixtures returned for the chosen window. Try more days or check your API plan.')
    st.stop()
with st.spinner('Comparing available odds…'):
    odds,odds_notes=load_odds(odds_key)
if odds_notes:st.info(odds_notes)
df=candidates(fixtures,history,odds)
if df.empty:
    st.error('Insufficient completed match history to estimate probabilities. This model requires at least 20 completed matches per league and 3 recent home/away samples per team.')
    st.stop()
st.subheader('Parlay research scenarios')
st.caption('Conservative = 2 legs ≥70%; Balanced = 3 legs ≥60%; Aggressive = 5 legs ≥52%. These labels do not imply safety. Different matches only; independence is an approximation.')
parlays=build_parlays(df)
if not parlays:st.warning('No combinations passed the current thresholds. If odds are connected, the system requires positive estimated value on every leg. No selection is a valid result.')
for item in parlays:
    with st.container(border=True):
        st.markdown(f"### {item['name']} — {len(item['legs'])} legs")
        st.write(f"**Model-estimated combined probability:** {item['probability']:.1%} | **Combined decimal odds:** {item['odds']:.2f}" if item['odds'] else f"**Model-estimated combined probability:** {item['probability']:.1%} | **Combined odds:** unavailable")
        if item['ev'] is not None:st.write(f"**Estimated return per unit staked:** {item['ev']:+.1%} (highly sensitive to model error)")
            legs_df = pd.DataFrame(item['legs'])[
                ['match', 'market', 'probability', 'odds', 'bookmaker', 'kickoff_utc']
            ]
            st.dataframe(legs_df, use_container_width=True, hide_index=True)
st.subheader('All modeled selections')
league=st.selectbox('Competition',['All']+list(LEAGUES))
view=df if league=='All' else df[df.league==league]
view=view.sort_values('probability',ascending=False)
st.dataframe(view[['league','kickoff_utc','match','market','probability','odds','bookmaker','ev','expected_goals','sample']].style.format({'probability':'{:.1%}','odds':'{:.2f}','ev':'{:+.1%}'}),hide_index=True,use_container_width=True)
st.download_button('Download analysis CSV',df.to_csv(index=False).encode('utf-8'),file_name=f'football-analysis-{dt.date.today()}.csv',mime='text/csv')
st.divider()
st.caption('Method: home/away goals from up to 90 days of completed matches; shrunk team rates and independent Poisson goal estimates. No injury, lineup, xG, weather, or live-news inputs. Odds matching may miss teams due to naming differences. Estimates are unvalidated and should not be treated as profitable betting signals.')
