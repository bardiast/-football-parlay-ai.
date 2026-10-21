import os
import datetime as dt
import pandas as pd
import streamlit as st
from engine import LEAGUES, fixtures_and_history, odds_lookup, candidates, build_parlays, odds_diagnostics
from analytics import backtest, metrics, calibration, snapshot, settle
from intelligence import match_intelligence, quote_quality, parlay_exposure, compare_to_baseline
import api_football as af

st.set_page_config(page_title="Football Probability Lab | Pro",page_icon="⚽",layout="wide",initial_sidebar_state="expanded")
st.markdown("""<style>
.stApp{background:#080d18;color:#eaf0fb}.block-container{max-width:1450px;padding-top:1.4rem;padding-bottom:4rem}
[data-testid="stSidebar"]{background:#0d1524;border-right:1px solid #22314a}
[data-testid="stMetric"]{background:#111c2e;border:1px solid #243550;border-radius:15px;padding:13px 16px}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:17px;border-color:#263750}
[data-testid="stTabs"] button{font-size:1rem;font-weight:650}
h1,h2,h3{letter-spacing:-.035em}h1{font-size:2.2rem!important}h2{font-size:1.45rem!important}
.hero{padding:24px 28px;background:linear-gradient(105deg,#11383d,#15223b 55%,#1b1b3a);border:1px solid #34535b;border-radius:20px;margin:0 0 18px}
.hero h1{margin:4px 0 5px}.hero p{margin:0;color:#b4c4d8}.eyebrow{font-size:.76rem;font-weight:750;letter-spacing:.13em;color:#6ce5b5}
.pill{display:inline-block;background:#17372f;border:1px solid #2e6a59;color:#a4f2d0;border-radius:999px;padding:3px 10px;font-size:.76rem;font-weight:650}
.muted{color:#98abc5;font-size:.9rem}.section{margin:18px 0 8px;font-weight:750;font-size:1.25rem}
</style>""",unsafe_allow_html=True)
st.markdown('<div class="hero"><span class="eyebrow">PRO EXPERIENCE · FOOTBALL RESEARCH</span><h1>⚽ Football Probability Lab</h1><p>Find fixtures. Understand probabilities. Compare real prices. Build your own scenarios.</p></div>',unsafe_allow_html=True)

@st.cache_data(ttl=1800,show_spinner=False)
def live_fixtures(token,days): return fixtures_and_history(token,days)
@st.cache_data(ttl=1800,show_spinner=False)
def live_odds(token): return odds_lookup(token)
@st.cache_data(ttl=86400,show_spinner=False)
def archive(token,leagues,season): return af.archive_history(token,list(leagues),season)

with st.sidebar:
    st.markdown('### ⚙️ Your workspace')
    view=st.segmented_control('Display mode',['Simple','Advanced'],default='Simple',key='view_mode')
    days=st.slider('Upcoming days',1,7,5)
    selected=st.multiselect('Competitions',list(LEAGUES),default=list(LEAGUES))
    priced_only=st.toggle('Verified odds only',value=True)
    min_samples=st.slider('Minimum team history',3,15,6,help='Minimum relevant completed matches per team. A higher setting reduces coverage.')
    with st.expander('🔐 API connections',expanded=False):
        football_key=st.text_input('football-data.org token',value=os.getenv('FOOTBALL_DATA_TOKEN',''),type='password')
        odds_key=st.text_input('The Odds API key',value=os.getenv('ODDS_API_KEY',''),type='password')
        api_key=st.text_input('API-Football key',value=os.getenv('API_FOOTBALL_KEY',''),type='password')
        st.caption('Current matches: football-data.org · Prices: The Odds API · Older archive: API-Football (optional).')
    if st.button('↻ Refresh data',use_container_width=True):
        st.cache_data.clear();st.rerun()
    st.caption('Research estimates only. A high probability is not a guarantee or a validated betting edge.')

if not football_key:
    st.info('Enter your football-data.org token in **API connections** in the sidebar to get started.')
    st.stop()
with st.spinner('Loading fixtures and bookmaker prices…'):
    fixtures,history,fixture_note=live_fixtures(football_key,days)
    odds,odds_note=live_odds(odds_key)
fixtures=[f for f in fixtures if f['league'] in selected]
bookmakers=sorted({b for event in odds.values() if isinstance(event,dict) for b in event.get('by_bookmaker',{})})
with st.sidebar:
    bookmaker=st.selectbox('Bookmaker',['Best available (mixed)']+bookmakers,help='Choose a specific bookmaker to avoid mixing prices from different sportsbooks.')
    if view=='Advanced':
        with st.expander('Data health',expanded=False):
            st.write(f'Fixtures: {len(fixtures)} · Historical results: {len(history)} · Odds events: {len(odds)}')
            if fixture_note:st.warning(fixture_note)
            if odds_note:st.info(odds_note)
            st.caption('Fixtures and odds cached for 30 minutes. Archive is on demand.')
with st.spinner('Estimating match probabilities…'):
    df=candidates(fixtures,history,odds,min_samples=min_samples,bookmaker=None if bookmaker.startswith('Best available') else bookmaker)
if df.empty:
    st.warning('No modeled selections for these settings. Try more days or reduce the minimum team history.')
    with st.expander('Connection diagnostics'):
        st.write(odds_diagnostics(fixtures,odds)['summary'])
        if fixture_note:st.write(fixture_note)
    st.stop()
df['probability']=pd.to_numeric(df['probability'],errors='coerce')
df['odds']=pd.to_numeric(df['odds'],errors='coerce')
quoted=df[df['odds'].gt(1)].copy()
q=quote_quality(quoted) if not quoted.empty else pd.DataFrame()
shown=df[df['odds'].gt(1)].copy() if priced_only else df.copy()
if 'saved_legs' not in st.session_state:st.session_state.saved_legs={}
if 'watchlist' not in st.session_state:st.session_state.watchlist=[]

def leg_key(row):return str(row['match_id'])+'|'+str(row['market'])
def add_leg(row):
    key=leg_key(row)
    if key not in st.session_state.saved_legs:
        st.session_state.saved_legs[key]={k:(v.item() if hasattr(v,'item') else v) for k,v in row.items()}
def evidence(row):
    sample=str(row.get('sample','0/0'))
    try:n=min(int(float(x)) for x in sample.split('/'))
    except (ValueError,TypeError):n=0
    return 'Broader' if n>=12 else ('Moderate' if n>=6 else 'Limited')
def render_fixture(row,prefix,show_add=True):
    with st.container(border=True):
        a,b,c=st.columns([4.5,1.6,1.8],vertical_alignment='center')
        with a:
            st.markdown(f"**{row['match']}**")
            st.caption(f"{row['league']} · {str(row['kickoff_utc'])[:16]} UTC")
            st.write(f"{row['market']} · Evidence: **{evidence(row)}**")
        with b:
            st.metric('Model estimate',f"{float(row['probability']):.0%}")
            st.caption('Uncalibrated')
        with c:
            st.metric('Bookmaker price',f"{float(row['odds']):.2f}×" if pd.notna(row['odds']) else 'Not available')
            if show_add and st.button('＋ Add to builder',key=prefix+leg_key(row),use_container_width=True):
                add_leg(row);st.toast('Added to your parlay builder')

t1,t2,t3,t4=st.tabs(['🏠 Discover','⚽ Match Analysis','🎯 Parlay Builder','📊 Performance'])
with t1:
    a,b,c,d=st.columns(4)
    a.metric('Upcoming matches',len(fixtures))
    b.metric('Analyzed matches',df['match_id'].nunique())
    c.metric('Matches with prices',quoted['match_id'].nunique())
    d.metric('Priced markets',len(quoted))
    st.markdown('<div class="section">Find a match</div>',unsafe_allow_html=True)
    fa,fb,fc=st.columns([2.3,1.3,1.4])
    with fa:search=st.text_input('Search team',placeholder='Search Arsenal, Barcelona, Madrid…',key='discover_search')
    with fb:league_filter=st.selectbox('Competition',['All']+selected,key='discover_league')
    with fc:sort=st.selectbox('Sort by',['Highest probability','Highest odds','Soonest kickoff'],key='discover_sort')
    markets=sorted(df['market'].unique())
    market_filter=st.multiselect('Markets',markets,default=[],placeholder='All markets')
    filtered=shown.copy()
    if search:filtered=filtered[filtered['match'].str.contains(search,case=False,regex=False,na=False)]
    if league_filter!='All':filtered=filtered[filtered['league']==league_filter]
    if market_filter:filtered=filtered[filtered['market'].isin(market_filter)]
    filtered=filtered.sort_values({'Highest probability':'probability','Highest odds':'odds','Soonest kickoff':'kickoff_utc'}[sort],ascending=sort=='Soonest kickoff')
    top=filtered.drop_duplicates('match_id').head(12)
    st.caption(f'{len(filtered)} matching selections · showing one featured market per fixture. Predictions are not calibrated.')
    if top.empty:st.info('No matches meet these filters. Try disabling Verified odds only.')
    for i,(_,row) in enumerate(top.iterrows()):render_fixture(row,f'discover_{i}_')
    if view=='Advanced':
        with st.expander('All selections & raw data'):
            st.dataframe(filtered,use_container_width=True,hide_index=True)
            st.download_button('Export selections CSV',filtered.to_csv(index=False),file_name='selections.csv',mime='text/csv')
        with st.expander('Odds connection diagnostics'):
            diagnostic=odds_diagnostics(fixtures,odds)
            st.write(diagnostic['summary'])
            if diagnostic['examples']:st.dataframe(pd.DataFrame(diagnostic['examples']),hide_index=True)

with t2:
    st.markdown('### Match Analysis')
    st.caption('Pick a fixture to explore its available markets, model assumptions and team history.')
    options=sorted(df['match'].unique())
    match_name=st.selectbox('Fixture',options,key='match_explorer')
    detail_df=df[df['match']==match_name].sort_values('probability',ascending=False)
    first=detail_df.iloc[0]
    aa,bb,cc=st.columns(3)
    aa.metric('Estimated goals (home–away)',first['expected_goals'])
    bb.metric('Team history samples',first['sample'])
    cc.metric('Evidence quality',evidence(first))
    st.markdown('#### Markets for this match')
    for i,(_,row) in enumerate(detail_df.head(12).iterrows()):render_fixture(row,f'match_{i}_')
    fixture=next((f for f in fixtures if str(f['id'])==str(first['match_id'])),None)
    if fixture:
        context=match_intelligence(fixture,history,min_samples=min_samples)
        if context:
            st.markdown('#### Form and schedule')
            x,y,z,w=st.columns(4)
            x.metric('Home Elo (context)',context['home_elo']);y.metric('Away Elo (context)',context['away_elo'])
            z.metric('Home rest (days)',context['home_rest_days'] if context['home_rest_days'] is not None else 'Unknown')
            w.metric('Away rest (days)',context['away_rest_days'] if context['away_rest_days'] is not None else 'Unknown')
            st.write('**Home last five:**',context['home_form'],' · **Away last five:**',context['away_form'])
            st.caption('Elo ratings are diagnostic and do not directly change the goal model. Rest days may be unavailable.')
    if not q.empty:
        prices=q[q['match']==match_name]
        if not prices.empty:
            with st.expander('Bookmaker vs model',expanded=view=='Advanced'):
                st.dataframe(prices[['market','probability','odds','bookmaker','implied_probability','model_market_gap_pp','evidence_grade']],hide_index=True,use_container_width=True)
                st.caption('Model-market gaps are not validated expected value. Bookmaker implied probabilities include margin.')
    st.info('Limitations: no confirmed lineups, verified injuries or shot-based xG. Cross-league strength is not calibrated; probabilities are estimates, not guarantees.')

with t3:
    st.markdown('### Parlay Builder')
    st.caption('Choose a strategy or build manually. Every leg comes from an actual modeled market; bookmaker prices are never invented.')
    strategy=st.radio('Approach',['Conservative','Balanced','Aggressive · High Odds','Aggressive · Model Value','Custom'],horizontal=True)
    with st.expander('⚙️ Strategy options',expanded=strategy=='Custom'):
        p1,p2,p3=st.columns(3)
        with p1:alternatives=st.slider('Alternatives',1,5,3)
        with p2:custom_legs=st.slider('Custom legs',2,6,4)
        with p3:custom_min=st.slider('Minimum custom probability',.20,.85,.40,.05)
        target=st.slider('Target combined odds (custom)',2.,30.,8.,.5)
        diversify=st.toggle('Prefer different leagues',value=True)
        require=st.toggle('Only use verified bookmaker prices',value=priced_only)
    parlays=build_parlays(df,require_odds=require,diversify=diversify,max_per_strategy=alternatives,
                         custom_legs=custom_legs,custom_min_probability=custom_min,custom_target_odds=target)
    matches=[p for p in parlays if p['name']==strategy]
    if not matches:st.info('Not enough distinct eligible matches for this strategy. Extend the fixture window or inspect unpriced markets.')
    for item in matches:
        with st.container(border=True):
            st.markdown(f"#### {strategy} · Option {item['variant']}")
            a,b,c=st.columns(3)
            a.metric('Combined odds',f"{item['odds']:.2f}×" if item['odds'] is not None else 'Unavailable')
            b.metric('Model joint estimate',f"{item['probability']:.1%}")
            c.metric('Legs',len(item['legs']))
            for leg in item['legs']:
                st.write(f"• **{leg['match']}** — {leg['market']} · {leg['probability']:.0%} · "+(f"{leg['odds']:.2f}×" if pd.notna(leg['odds']) else 'No price'))
            if item['bookmakers']>1:st.warning('Mixed bookmakers: this combined price may not exist at one sportsbook.')
            if st.button('＋ Copy these legs to manual builder',key=f"copy_{strategy}_{item['variant']}"):
                for leg in item['legs']:add_leg(leg)
                st.toast('Scenario added to manual builder')
    st.divider()
    st.markdown('#### Your manual parlay')
    saved=st.session_state.saved_legs
    if not saved:st.info('Add markets from Discover, Match Analysis, or a strategy above.')
    else:
        rows=list(saved.items());selected_ids=[str(r.get('match_id')) for _,r in rows]
        duplicates=len(set(selected_ids))!=len(selected_ids)
        total=1.;joint=1.;all_priced=True;books=set()
        for key,row in rows:
            col1,col2=st.columns([6,1],vertical_alignment='center')
            col1.write(f"**{row['match']}** · {row['market']} · {float(row['probability']):.0%} · "+(f"{float(row['odds']):.2f}×" if pd.notna(row['odds']) else 'Unpriced'))
            if col2.button('Remove',key='remove_'+key):del saved[key];st.rerun()
            joint*=float(row['probability'])
            if pd.notna(row['odds']):total*=float(row['odds']);books.add(str(row.get('bookmaker') or 'Unknown'))
            else:all_priced=False
        if duplicates:st.error('Multiple markets from the same fixture: joint probability cannot be calculated by multiplying these legs.')
        elif len(books)>1:st.warning('Multiple bookmakers: the combined price may not be available on one betslip.')
        c1,c2=st.columns(2)
        c1.metric('Combined verified odds',f'{total:.2f}×' if all_priced else 'Incomplete')
        c2.metric('Naïve joint model estimate',f'{joint:.1%}' if not duplicates else 'Not applicable')
        st.caption('Joint estimates assume independence between fixtures and are not calibrated. Related markets are not multiplied.')
        export=pd.DataFrame([r for _,r in rows])
        st.download_button('⬇ Export your parlay',export.to_csv(index=False),file_name='my-parlay.csv',mime='text/csv')
        if st.button('Clear manual parlay'):saved.clear();st.rerun()
    if view=='Advanced':
        with st.expander('Parlay exposure across generated strategies'):
            _,exposure=parlay_exposure(parlays)
            if not exposure.empty:st.dataframe(exposure,hide_index=True,use_container_width=True)
            else:st.info('No scenarios to audit.')

with t4:
    st.markdown('### Performance')
    st.caption('Historical evaluation and pre-kickoff prediction exports. Backtests do not establish profitable betting performance.')
    @st.cache_data(ttl=1800,show_spinner=False)
    def cached_bt(rows,minimum,limit):return backtest([dict(r) for r in rows],minimum,limit)
    with st.expander('Backtest filters',expanded=False):
        limit=st.slider('Historical matches',50,500,240,50)
        market=st.selectbox('Market',sorted(df['market'].unique()))
        league=st.selectbox('Competition',['All']+list(LEAGUES),key='bt_league')
    history_rows=tuple(tuple(sorted(row.items())) for row in history)
    bt=cached_bt(history_rows,min_samples,limit)
    if not bt.empty:
        bt=bt[bt['market']==market]
        if league!='All':bt=bt[bt['league']==league]
    if bt.empty:st.info('Not enough historical observations for these filters.')
    else:
        summary=metrics(bt)
        a,b,c=st.columns(3)
        a.metric('Evaluated matches',summary['matches'])
        b.metric('Brier score · lower better',f"{summary['brier']:.3f}")
        c.metric('Observed occurrence',f"{summary['observed_rate']:.1%}")
        cal=calibration(bt)
        if not cal.empty:
            st.markdown('#### Calibration overview')
            st.bar_chart(cal.set_index('bucket')[['predicted','observed']])
        if view=='Advanced':
            benchmark=compare_to_baseline(bt)
            if benchmark:st.caption(f"Model Brier: {benchmark['model_brier']:.3f} · Constant-prevalence diagnostic: {benchmark['constant_prevalence_brier']:.3f}. {benchmark['note']}")
            with st.expander('Historical predictions'):st.dataframe(bt,hide_index=True,use_container_width=True)
        st.download_button('⬇ Export backtest',bt.to_csv(index=False),file_name='backtest.csv',mime='text/csv')
    st.divider()
    st.markdown('#### Save and settle predictions')
    now=dt.datetime.now(dt.timezone.utc)
    future=df[pd.to_datetime(df['kickoff_utc'],utc=True,errors='coerce')>now]
    if not future.empty:
        st.download_button('⬇ Save predictions before kickoff',snapshot(future).to_csv(index=False),file_name=f'predictions-{now:%Y%m%d-%H%M}-utc.csv',mime='text/csv')
    else:st.info('No future fixtures available to save.')
    uploaded=st.file_uploader('Upload a previously saved predictions CSV',type='csv')
    if uploaded is not None:
        try:
            saved_df=pd.read_csv(upload)
            needed={'match_id','market','kickoff_utc','recorded_at_utc'}
            if not needed.issubset(saved_df.columns):st.error('Missing required fields: '+', '.join(sorted(needed-set(saved_df.columns))))
            else:
                settled=settle(saved_df,history)
                st.dataframe(settled,hide_index=True,use_container_width=True)
                st.download_button('⬇ Export settled predictions',settled.to_csv(index=False),file_name='settled.csv',mime='text/csv')
        except (ValueError,pd.errors.ParserError) as e:st.error(f'Could not read CSV: {e}')
    with st.expander('🗄️ API-Football archive (optional; free-tier seasons only)'):
        season=st.selectbox('Season starting year',[2024,2023,2022])
        if not api_key:st.info('Enter your API-Football key in sidebar → API connections.')
        elif not selected:st.info('Select at least one competition.')
        else:
            if st.button('Load archive · uses API quota'):
                with st.spinner('Fetching older historical data…'):
                    result=archive(api_key,tuple(selected),season)
                st.session_state.archive_result=(result,season,tuple(selected))
            state=st.session_state.get('archive_result')
            if state and state[1:]==(season,tuple(selected)):
                (records,warnings,remaining),_,_=state
                st.metric('Finished archived matches',len(records))
                if warnings:st.warning('; '.join(warnings))
                if records:
                    data=pd.DataFrame(records)
                    st.dataframe(data.groupby('league').agg(matches=('id','count')).reset_index(),hide_index=True)
                    st.download_button('⬇ Export archive',data.to_csv(index=False),file_name=f'archive-{season}.csv',mime='text/csv')
                st.caption(f'Remaining requests reported: {remaining or "unknown"}')
    st.caption('Predictions are stored only in downloaded CSVs. Streamlit session state and temporary files are not durable storage.')

st.divider()
st.caption('Football-data.org supplies current results; The Odds API supplies available prices; API-Football archives are separate. Estimates are uncalibrated and do not incorporate confirmed injuries, lineups or genuine shot-based xG. Never assume a model-market discrepancy implies a profitable opportunity.')
