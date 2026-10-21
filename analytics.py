"""Leakage-safe historical evaluation and portable prediction snapshots."""
import datetime as dt
import math
import pandas as pd
from engine import estimate

MARKETS = ('Home win','Draw','Away win','1X (home or draw)','X2 (away or draw)',
           'Over 1.5 goals','Over 2.5 goals','Under 3.5 goals','Both teams score',
           'Home scores','Away scores')

def outcome(market, home, away):
    return {'Home win':home>away,'Draw':home==away,'Away win':home<away,
            '1X (home or draw)':home>=away,'X2 (away or draw)':home<=away,
            'Over 1.5 goals':home+away>=2,'Over 2.5 goals':home+away>=3,
            'Under 3.5 goals':home+away<=3,'Both teams score':home>0 and away>0,
            'Home scores':home>0,'Away scores':away>0}[market]

def backtest(history, min_samples=6, max_matches=240):
    """Walk-forward evaluation: each match sees only results preceding kickoff.

    No odds or ROI inferred; fixture history may be incomplete due to API quotas.
    """
    completed=sorted((r for r in history if isinstance(r.get('hg'),int) and isinstance(r.get('ag'),int)),
                     key=lambda r:r.get('date',''))
    results=[]
    for match in completed[-max_matches:]:
        model=estimate(match,completed,min_samples=min_samples)
        if model is None:continue
        probs,lh,la,nh,na,quality,dh,da=model
        for market,p in probs.items():
            results.append({'date':match['date'],'league':match['league'],
                            'match':f"{match['home']} vs {match['away']}",
                            'match_id':match['id'],'market':market,'probability':float(p),
                            'actual':int(outcome(market,match['hg'],match['ag'])),
                            'sample_quality':quality,'predicted_home_goals':lh,'predicted_away_goals':la})
    return pd.DataFrame(results)

def metrics(frame):
    if frame.empty:return {}
    p=frame['probability'].astype(float)
    y=frame['actual'].astype(float)
    return {'predictions':len(frame),'matches':frame['match_id'].nunique(),
            'brier':float(((p-y)**2).mean()),
            'accuracy_at_50':float(((p>=.5)==(y==1)).mean()),
            'mean_forecast':float(p.mean()),'observed_rate':float(y.mean())}

def calibration(frame):
    if frame.empty:return pd.DataFrame()
    d=frame.copy()
    d['bucket']=pd.cut(d['probability'],bins=[0,.1,.2,.3,.4,.5,.6,.7,.8,.9,1.000001],
                       labels=['0–10%','10–20%','20–30%','30–40%','40–50%',
                               '50–60%','60–70%','70–80%','80–90%','90–100%'],include_lowest=True)
    return d.groupby('bucket',observed=True).agg(n=('actual','size'),
           predicted=('probability','mean'),observed=('actual','mean')).reset_index()

def snapshot(frame):
    """Portable CSV of pre-kickoff predictions. User must save externally."""
    cols=['match_id','league','kickoff_utc','match','market','probability','odds','bookmaker',
          'sample','sample_quality']
    result=frame[[c for c in cols if c in frame.columns]].copy()
    result['recorded_at_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    return result

def settle(snapshot_frame,history):
    """Settle saved predictions against actual scores; no fabricated settlement."""
    results={str(r['id']):r for r in history if isinstance(r.get('hg'),int) and isinstance(r.get('ag'),int)}
    out=snapshot_frame.copy()
    statuses=[]
    for _,row in out.iterrows():
        m=results.get(str(row.get('match_id')))
        if not m or row.get('market') not in MARKETS:
            statuses.append('Pending / unavailable');continue
        try:
            # Never settle a prediction recorded after kickoff.
            recorded=pd.to_datetime(row.get('recorded_at_utc'),utc=True)
            kickoff=pd.to_datetime(row.get('kickoff_utc'),utc=True)
            if pd.isna(recorded) or pd.isna(kickoff) or recorded>=kickoff:
                statuses.append('Invalid timing');continue
            statuses.append('Won' if outcome(row['market'],m['hg'],m['ag']) else 'Lost')
        except (TypeError,ValueError,KeyError):statuses.append('Invalid timing')
    out['result']=statuses
    return out
