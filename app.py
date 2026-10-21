import os
import datetime as dt
import pandas as pd
import streamlit as st
from engine import LEAGUES, fixtures_and_history, odds_lookup, candidates, build_parlays, odds_diagnostics
from analytics import backtest, metrics, calibration, snapshot, settle

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
    min_samples=st.slider('Minimum matches per team (all competitions)',3,15,6)
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
bookmakers=sorted({book for event in odds.values() for book in event.get('by_bookmaker',{})})
with st.sidebar:
    bookmaker_choice=st.selectbox('Bookmaker pricing mode',['Best available across bookmakers']+bookmakers,
        help='Select one bookmaker for a realizable same-bookmaker parlay price. Best available can combine different sportsbooks.')
with st.spinner('Estimating outcomes…'):
    df=candidates(fixtures,history,odds,min_samples=min_samples,
                  bookmaker=None if bookmaker_choice.startswith('Best available') else bookmaker_choice)


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

st.subheader('🎯 Parlay research studio')
st.caption('Four distinct strategies · up to five alternatives each · one market per match · model probabilities are uncalibrated.')
with st.expander('⚙️ Scenario controls',expanded=False):
    ca,cb,cc=st.columns(3)
    with ca: variants=st.slider('Alternatives per strategy',1,5,3)
    with cb: custom_legs=st.slider('Custom legs',2,6,4)
    with cc: custom_min=st.slider('Custom minimum model probability',.20,.85,.40,.05)
    custom_target=st.slider('Custom target decimal odds',2.,30.,8.,.5)
    st.caption('Targets are preferences, not promises. A scenario may fall outside its target when the available markets are limited.')
parlays=build_parlays(df,require_odds=only_priced,diversify=diverse,
                     max_per_strategy=variants,custom_legs=custom_legs,
                     custom_min_probability=custom_min,custom_target_odds=custom_target)
priced_count=int(df['odds'].notna().sum())
priced_matches=int(df.loc[df['odds'].notna(),'match_id'].nunique())
st.caption(f'Available: {len(df)} modeled markets · {priced_count} priced markets across {priced_matches} distinct priced fixtures. '
           'Five-leg parlays require at least five different priced fixtures when verified odds are enabled.')
if not parlays:
    st.warning('No complete scenarios from available fixtures. Check the distinct priced match count and odds diagnostics; unpriced markets cannot supply combined bookmaker odds.')
else:
    names=['Conservative','Balanced','Aggressive · High Odds','Aggressive · Model Value','Custom']
    tabs=st.tabs(['🟢 Conservative','🟡 Balanced','🔴 High odds','🟣 Model value','🛠 Custom'])
    for tab,name in zip(tabs,names):
        with tab:
            items=[p for p in parlays if p['name']==name]
            if not items:
                st.info('Not enough distinct eligible matches for this strategy. Try a longer fixture window, or inspect unpriced markets with the verified-odds toggle off.')
                continue
            for item in items:
                with st.container(border=True):
                    st.markdown(f"#### Scenario {item['variant']} · {len(item['legs'])} legs")
                    x,y,z=st.columns(3)
                    x.metric('Combined bookmaker odds',f"{item['odds']:.2f}×" if item['odds'] is not None else 'Unavailable')
                    y.metric('Uncalibrated joint estimate',f"{item['probability']:.1%}")
                    z.metric('Preferred odds range',item['target'])
                    if item['odds'] is not None:
                        st.caption(f"Model-implied discrepancy vs quoted price: {item['model_edge']:+.1%} (NOT validated expected value).")
                    if item['bookmakers']>1:
                        st.warning('Prices come from different bookmakers; this combined price may not be available on any single betslip.')
                    st.caption('Joint probability multiplies leg estimates and assumes independence across matches; no uncertainty calibration or demonstrated edge.')
                    for leg in item['legs']:
                        price_text=f"{leg['odds']:.2f}×" if pd.notna(leg['odds']) else 'Unpriced'
                        st.markdown(f"**{leg['match']}** · {leg['market']}")
                        st.caption(f"{leg['league']} · {leg['probability']:.1%} model estimate · {price_text} · {leg['bookmaker'] or 'No bookmaker'} · sample {leg['sample']} ({leg['sample_quality']})")
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
    display_cols=['league','kickoff_utc','match','market','probability','odds','bookmaker','sample','sample_quality','domestic_samples']
    st.dataframe(show[display_cols],use_container_width=True,hide_index=True,column_config={
        'league':'Competition','kickoff_utc':'Kickoff (UTC)','match':'Fixture','market':'Market',
        'probability':st.column_config.NumberColumn('Estimated probability',format='%.1f%%'),
        'odds':st.column_config.NumberColumn('Decimal odds',format='%.2f'),
        'ev':st.column_config.NumberColumn('Model EV',format='%.1f%%'),
        'sample':'Team match samples','sample_quality':'Sample coverage','domestic_samples':'Domestic samples'},
        column_order=display_cols)

st.subheader('🧠 Match intelligence')
match_names=sorted(df['match'].unique())
selected_match=st.selectbox('Explore fixture',match_names,key='explorer_match')
analysis=df[df['match']==selected_match].sort_values('probability',ascending=False)
if not analysis.empty:
    first=analysis.iloc[0]
    col1,col2,col3=st.columns(3)
    col1.metric('Model expected goals (home–away)',first['expected_goals'])
    col2.metric('Historical team samples',first['sample'])
    col3.metric('Evidence coverage',first['sample_quality'])
    st.dataframe(analysis[['market','probability','odds','bookmaker','ev']].rename(columns={
        'probability':'Model probability','ev':'Model/price discrepancy'}),hide_index=True,use_container_width=True,
        column_config={'Model probability':st.column_config.NumberColumn(format='%.1f%%'),
                       'Model/price discrepancy':st.column_config.NumberColumn(format='%.1%')})
    st.caption('Supporting evidence: prior team results and recency-weighted goal rates. Caution: no verified injuries, lineups or shot-based xG; domestic-vs-European strength is not calibrated.')

st.subheader('📈 Historical backtest')
st.caption('Walk-forward predictions on historical finished matches. Each forecast uses only results dated before kickoff. No historical odds are invented.')
@st.cache_data(ttl=1800,show_spinner=False)
def cached_backtest(history_rows, minimum, limit):
    return backtest([dict(row) for row in history_rows],minimum,limit)
with st.expander('Backtest settings',expanded=False):
    backtest_limit=st.slider('Historical matches to evaluate',50,500,240,50)
    backtest_market=st.selectbox('Backtest market',sorted(df['market'].unique()))
    backtest_league=st.selectbox('Backtest competition',['All']+list(LEAGUES))
with st.spinner('Evaluating historical predictions…'):
    history_rows=tuple(tuple(sorted(row.items())) for row in history)
    # Restore dictionaries after creating a hashable cache input.
    bt=cached_backtest(history_rows,min_samples,backtest_limit)
if not bt.empty:
    bt=bt[bt['market']==backtest_market]
    if backtest_league!='All':bt=bt[bt['league']==backtest_league]
    summary=metrics(bt)
    if summary:
        q1,q2,q3,q4=st.columns(4)
        q1.metric('Evaluated matches',summary['matches'])
        q2.metric('Brier score (lower better)',f"{summary['brier']:.3f}")
        q3.metric('50% threshold accuracy',f"{summary['accuracy_at_50']:.1%}")
        q4.metric('Actual occurrence rate',f"{summary['observed_rate']:.1%}")
        cal=calibration(bt)
        if not cal.empty:
            st.caption('Calibration: average predicted probability vs observed frequency by probability band.')
            st.bar_chart(cal.set_index('bucket')[['predicted','observed']])
        with st.expander('Historical prediction rows'):
            st.dataframe(bt[['date','league','match','probability','actual']],hide_index=True,use_container_width=True)
        st.download_button('⬇️ Export backtest CSV',bt.to_csv(index=False),file_name='backtest.csv',mime='text/csv')
    else:st.info('No historical predictions for this filter.')
else:st.info('Insufficient eligible historical data for walk-forward evaluation. Increase historical coverage or reduce minimum samples.')
st.caption('Backtest caveat: data provider coverage can omit historical fixtures, and repeatedly comparing strategies on the same sample can overfit. No forward performance or profitable edge is established.')

st.subheader('🗂️ Prediction tracking')
st.caption('Export a timestamped snapshot BEFORE kickoff, keep the CSV yourself, then upload it later to settle against available completed scores. Streamlit does not permanently store these predictions.')
now=dt.datetime.now(dt.timezone.utc)
future=df[pd.to_datetime(df['kickoff_utc'],utc=True)>now]
if not future.empty:
    st.download_button('⬇️ Save pre-match predictions CSV',snapshot(future).to_csv(index=False).encode('utf-8'),
        file_name=f'predictions-{now:%Y%m%d-%H%M}-utc.csv',mime='text/csv')
else:st.info('No future fixtures currently available to snapshot.')
upload=st.file_uploader('Upload a previously saved predictions CSV',type='csv')
if upload is not None:
    try:
        saved=pd.read_csv(upload)
        required={'match_id','market','kickoff_utc','recorded_at_utc'}
        if not required.issubset(saved.columns):
            st.error('This CSV is missing required snapshot fields: '+', '.join(sorted(required-saved.columns)))
        else:
            settled=settle(saved,history)
            st.dataframe(settled,hide_index=True,use_container_width=True)
            st.download_button('⬇️ Download settled results',settled.to_csv(index=False),file_name='settled-predictions.csv',mime='text/csv')
    except (ValueError,pd.errors.ParserError) as exc:st.error(f'Unable to read snapshot: {exc}')

st.download_button('⬇️ Download analysis CSV',df.to_csv(index=False).encode('utf-8'),file_name=f'football-analysis-{dt.date.today()}.csv',mime='text/csv')
st.divider()
st.caption('Research only: high odds imply low hit rates; model-implied value is not verified profit. Method: last 365 days of cross-competition team results, recency weighting, strong shrinkage, and independent Poisson scoring. Opponent strength is NOT adjusted: domestic and European results may not be comparable. Sample coverage is not statistical confidence. No shot-based xG, injuries or lineups. Historical walk-forward evaluation is descriptive, not probability calibration. Prices may be from different bookmakers and cannot necessarily be combined.')
