import os
import datetime as dt
import pandas as pd
import streamlit as st
from engine import LEAGUES, fixtures_and_history, odds_lookup, candidates, build_parlays, odds_diagnostics

st.set_page_config(page_title='Football Probability Lab', page_icon='⚽', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
.stApp {background: #0b1020; color: #e8edf7;}
.block-container {padding-top: 2rem; max-width: 1450px;}
[data-testid="stMetric"] {background:#151e33;border:1px solid #293652;border-radius:14px;padding:16px;}
[data-testid="stVerticalBlockBorderWrapper"] {background:#111a2c;border-radius:16px;}
h1,h2,h3 {letter-spacing:-.025em;}
.hero {padding:24px 26px;background:linear-gradient(115deg,#173a44,#15213b 60%,#181c3c);border:1px solid #35505c;border-radius:18px;margin-bottom:20px;}
.hero h1 {margin:0;font-size:2.3rem;}.hero p {margin:8px 0 0;color:#b5c9d3;}
.badge {display:inline-block;border:1px solid #52796d;color:#a7efc5;padding:3px 9px;border-radius:20px;font-size:12px;}
</style>''', unsafe_allow_html=True)
st.markdown('<div class="hero"><span class="badge">FOOTBALL ANALYTICS • RESEARCH MODE</span><h1>⚽ Football Probability Lab</h1><p>Fixture analysis · Verifiable bookmaker prices · Transparent probability estimates</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header('⚙️ Data & filters')
    football_key=st.text_input('football-data.org token',value=os.getenv('FOOTBALL_DATA_TOKEN',''),type='password')
    odds_key=st.text_input('The Odds API key',value=os.getenv('ODDS_API_KEY',''),type='password')
    days=st.slider('Upcoming days',1,7,3)
    selected=st.multiselect('Competitions',list(LEAGUES),default=list(LEAGUES))
    diverse=st.toggle('Diversify leagues in each parlay',value=True,help='Prefer a mix of competitions when eligible selections exist; never override price or minimum probability rules.')
    only_priced=st.toggle('Require verified bookmaker odds',value=True,help='Parlays without bookmaker prices cannot show a combined decimal price.')
    min_samples=st.slider('Minimum home/away samples per team',3,10,3)
    if st.button('🔄 Refresh live data',use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption('Free-tier API coverage and request quotas vary. Data is cached for 30 minutes. Keys are not shown in reports.')

@st.cache_data(ttl=1800,show_spinner=False)
def get_fixtures(token,days):return fixtures_and_history(token,days)
@st.cache_data(ttl=1800,show_spinner=False)
def get_odds(token):return odds_lookup(token)

if not football_key:
    st.warning('Add your football-data.org token in the sidebar to begin.')
    st.stop()
with st.spinner('Loading fixtures and historical results…'):
    fixtures,history,fixture_notes=get_fixtures(football_key,days)
fixtures=[m for m in fixtures if m['league'] in selected]
if fixture_notes:st.warning('Fixture provider: '+fixture_notes)
with st.spinner('Checking bookmaker prices…'):
    odds,odds_notes=get_odds(odds_key)
if odds_notes:st.info(odds_notes)
with st.spinner('Estimating outcomes…'):
    df=candidates(fixtures,history,odds,min_samples=min_samples)

a,b,c,d=st.columns(4)
a.metric('Upcoming fixtures',len(fixtures))
b.metric('Completed matches',len(history))
c.metric('Available odds events',len(odds))
d.metric('Selections with prices',int(df['odds'].notna().sum()) if not df.empty else 0)

with st.expander('🔎 Odds connection diagnostics',expanded=bool(odds_key and (df.empty or df['odds'].notna().sum()==0))):
    diagnostic=odds_diagnostics(fixtures,odds)
    st.write(diagnostic['summary'])
    if diagnostic['examples']:
        st.dataframe(pd.DataFrame(diagnostic['examples']),hide_index=True,use_container_width=True)
    st.caption('A working API key does not guarantee the requested games, markets, or bookmakers are covered. Unmatched prices are never invented.')

if df.empty:
    st.warning('No eligible selections. Try a longer fixture window, different competitions, or a lower minimum sample threshold.')
    st.stop()

st.subheader('🎯 Parlay scenarios')
st.caption('Illustrative combinations, not recommendations. Combined probability assumes independence between matches; estimates have not been calibrated or backtested.')
parlays=build_parlays(df,require_odds=only_priced,diversify=diverse)
if not parlays:
    st.warning('No complete combinations satisfy the current filters. If bookmaker prices are required, check the odds diagnostics above. You can switch off “Require verified bookmaker odds” to explore unpriced scenarios.')
else:
    columns=st.columns(len(parlays))
    for col,item in zip(columns,parlays):
        with col:
            with st.container(border=True):
                st.markdown(f"### {item['name']}")
                st.caption(f"{len(item['legs'])} distinct matches")
                st.metric('Combined decimal odds',f"{item['odds']:.2f}×" if item['odds'] is not None else 'Unavailable')
                st.metric('Model-estimated probability',f"{item['probability']:.1%}")
                if item['ev'] is not None:st.caption(f"Unvalidated estimated EV: {item['ev']:+.1%}")
                for leg in item['legs']:
                    st.markdown(f"**{leg['match']}**")
                    price_text = f"{leg['odds']:.2f}×" if pd.notna(leg['odds']) else 'No price'
                    st.caption(f"{leg['league']} · {leg['market']} · {leg['probability']:.1%} estimated · {price_text}")
                    if pd.notna(leg['bookmaker']):st.caption(f"Bookmaker: {leg['bookmaker']}")
                    st.divider()

st.subheader('📋 All modeled selections')
show=df.copy()
if only_priced:show=show[show['odds'].notna()]
show=show.sort_values(['probability','league'],ascending=[False,True])
if show.empty:
    st.info('No selections with verified bookmaker prices. Disable “Require verified bookmaker odds” to inspect model-only outcomes.')
else:
    show['probability']=show['probability']*100
    show['ev']=show['ev']*100
    display_cols=['league','kickoff_utc','match','market','probability','odds','bookmaker','ev','sample']
    st.dataframe(show[display_cols],use_container_width=True,hide_index=True,column_config={
        'league':'Competition','kickoff_utc':'Kickoff (UTC)','match':'Fixture','market':'Market',
        'probability':st.column_config.NumberColumn('Estimated probability',format='%.1f%%'),
        'odds':st.column_config.NumberColumn('Decimal odds',format='%.2f'),
        'ev':st.column_config.NumberColumn('Model EV',format='%.1f%%'),
        'sample':'Home/away samples'},
        column_order=display_cols)

st.download_button('⬇️ Download analysis CSV',df.to_csv(index=False).encode('utf-8'),file_name=f'football-analysis-{dt.date.today()}.csv',mime='text/csv')
st.divider()
st.caption('Method: recent home/away goals with league-average shrinkage and independent Poisson scoring. No xG, injuries, lineups or real-time news. Estimated probabilities and EV are unvalidated and may be inaccurate. Bookmaker prices may change.')
