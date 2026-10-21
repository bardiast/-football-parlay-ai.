"""Auditable football research utilities. No betting advantage is asserted."""
import datetime as dt
import math
import pandas as pd


def parsed_date(value):
    try:
        t=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def elo_ratings(history, as_of=None, base=1500, k=22, home_advantage=55):
    """Chronological Elo based on completed matches; never uses post-cutoff results."""
    cutoff=parsed_date(as_of) if as_of is not None else None
    ratings={}; games={}
    for m in sorted(history,key=lambda r:r.get('date','')):
        when=parsed_date(m.get('date'))
        if when is None or (cutoff is not None and when>=cutoff):continue
        if not isinstance(m.get('hg'),int) or not isinstance(m.get('ag'),int):continue
        h,a=m.get('home_id'),m.get('away_id')
        if h is None or a is None or h==a:continue
        rh,ra=ratings.get(h,base),ratings.get(a,base)
        expected=1/(1+10**((ra-rh-home_advantage)/400))
        actual=1 if m['hg']>m['ag'] else (0 if m['hg']<m['ag'] else .5)
        # Moderate goal-difference weighting; capped to avoid runaway ratings.
        margin=min(2,1+.2*max(0,abs(m['hg']-m['ag'])-1))
        ratings[h]=rh+k*margin*(actual-expected)
        ratings[a]=ra-k*margin*(actual-expected)
        games[h]=games.get(h,0)+1;games[a]=games.get(a,0)+1
    return ratings,games


def match_intelligence(fixture, history, min_samples=6):
    from engine import estimate
    kickoff=parsed_date(fixture.get('date'))
    if kickoff is None:return None
    past=[r for r in history if (parsed_date(r.get('date')) or kickoff)>=dt.datetime(1970,1,1,tzinfo=dt.timezone.utc)
          and parsed_date(r.get('date')) is not None and parsed_date(r['date'])<kickoff]
    ratings,games=elo_ratings(past,fixture['date'])
    hid,aid=fixture.get('home_id'),fixture.get('away_id')
    rh,ra=ratings.get(hid,1500),ratings.get(aid,1500)
    elo_home=1/(1+10**((ra-rh-55)/400)) # expected points, NOT win probability
    prior_home=[r for r in past if hid in (r.get('home_id'),r.get('away_id'))]
    prior_away=[r for r in past if aid in (r.get('home_id'),r.get('away_id'))]
    def form(rows,team):
        out=[]
        for r in sorted(rows,key=lambda x:x['date'])[-5:]:
            hg,ag=r.get('hg'),r.get('ag')
            if not isinstance(hg,int) or not isinstance(ag,int):continue
            own,other=(hg,ag) if r.get('home_id')==team else (ag,hg)
            out.append('W' if own>other else 'D' if own==other else 'L')
        return ' · '.join(out) if out else 'Unavailable'
    last_h=max((parsed_date(r['date']) for r in prior_home if parsed_date(r.get('date'))),default=None)
    last_a=max((parsed_date(r['date']) for r in prior_away if parsed_date(r.get('date'))),default=None)
    model=estimate(fixture,past,min_samples=min_samples)
    return {'home_elo':round(rh),'away_elo':round(ra),'home_elo_matches':games.get(hid,0),
            'away_elo_matches':games.get(aid,0),'elo_expected_points_home':elo_home,
            'home_form':form(prior_home,hid),'away_form':form(prior_away,aid),
            'home_rest_days':(kickoff-last_h).days if last_h else None,
            'away_rest_days':(kickoff-last_a).days if last_a else None,
            'model_available':model is not None,'model':model}


def quote_quality(frame):
    if frame.empty:return frame.copy()
    d=frame.copy()
    d['implied_probability']=1/pd.to_numeric(d['odds'],errors='coerce')
    d['model_market_gap_pp']=(d['probability']-d['implied_probability'])*100
    d['sample_min']=pd.to_numeric(d['sample'].astype(str).str.split('/').str[0],errors='coerce').fillna(0)
    d['sample_min']=pd.concat([d['sample_min'],pd.to_numeric(d['sample'].astype(str).str.split('/').str[-1],errors='coerce').fillna(0)],axis=1).min(axis=1)
    d['evidence_score']=(d['sample_min']/20).clip(upper=1)*100
    d['evidence_grade']=pd.cut(d['evidence_score'],[-1,29,59,100],labels=['Limited','Moderate','Broader'])
    return d


def parlay_exposure(parlays):
    rows=[]
    for item in parlays:
        for leg in item['legs']:
            rows.append({'scenario':f"{item['name']} #{item['variant']}",
                         'match':leg['match'],'league':leg['league'],'market':leg['market']})
    if not rows:return pd.DataFrame(),pd.DataFrame()
    d=pd.DataFrame(rows)
    exposure=d.groupby(['match','market'],as_index=False).agg(appearances=('scenario','nunique'))
    return d,exposure.sort_values('appearances',ascending=False)


def compare_to_baseline(backtest_frame):
    if backtest_frame.empty:return {}
    y=backtest_frame['actual'].astype(float)
    p=backtest_frame['probability'].astype(float)
    # In-sample prevalence is diagnostic only, not an out-of-sample baseline.
    baseline=float(y.mean())
    return {'model_brier':float(((p-y)**2).mean()),'constant_prevalence_brier':float(((baseline-y)**2).mean()),
            'count':len(y),'note':'Constant-prevalence benchmark uses this evaluation sample; not a fair prospective baseline.'}
