"""Football analytics for research and paper-tracking, not wagering advice."""
import os, math, datetime as dt, re, unicodedata, difflib
import requests
import pandas as pd

LEAGUES = {'Premier League':'PL','La Liga':'PD','Bundesliga':'BL1','Serie A':'SA','Ligue 1':'FL1','Champions League':'CL'}
BASE='https://api.football-data.org/v4'

def fixtures_and_history(token, days=3):
    if not token: return [], [], 'Add a free football-data.org API token in the sidebar to load real fixtures.'
    headers={'X-Auth-Token':token}
    today=dt.datetime.now(dt.timezone.utc).date()
    fixtures=[]; history=[]; errors=[]
    for name, code in LEAGUES.items():
        try:
            r=requests.get(f'{BASE}/competitions/{code}/matches',headers=headers,params={'dateFrom':str(today-dt.timedelta(days=365)),'dateTo':str(today+dt.timedelta(days=days))},timeout=18)
            if not r.ok:
                errors.append(f'{name}: HTTP {r.status_code}'); continue
            for m in r.json().get('matches',[]):
                home=m.get('homeTeam') or {}; away=m.get('awayTeam') or {}
                row={'id':m.get('id'),'league':name,'date':m.get('utcDate'),'home':home.get('name'),'away':away.get('name'),'home_id':home.get('id'),'away_id':away.get('id'),'status':m.get('status')}
                if not row['home'] or not row['away']: continue
                if m.get('status')=='FINISHED':
                    score=(m.get('score') or {}).get('fullTime') or {}
                    if isinstance(score.get('home'),int) and isinstance(score.get('away'),int): history.append({**row,'hg':score['home'],'ag':score['away']})
                elif m.get('status') in ('SCHEDULED','TIMED') and today <= dt.datetime.fromisoformat(row['date'].replace('Z','+00:00')).date() <= today+dt.timedelta(days=days): fixtures.append(row)
        except (requests.RequestException,ValueError,KeyError) as exc: errors.append(f'{name}: {str(exc)[:100]}')
    return fixtures,history,'; '.join(errors)

def poisson(k, lam):
    return math.exp(-lam)*lam**k/math.factorial(k)

def _weighted_mean(records, field, reference, half_life=75):
    """Exponentially weight older matches, then shrink toward a competition baseline."""
    weights = []
    for row in records:
        try:
            age = max(0, (reference - dt.datetime.fromisoformat(row['date'].replace('Z', '+00:00'))).total_seconds() / 86400)
        except (ValueError, TypeError, AttributeError):
            continue
        weights.append((float(row[field]), 0.5 ** (age / half_life)))
    total = sum(w for _, w in weights)
    return sum(v*w for v,w in weights)/total if total else None


def estimate(match, history, min_samples=3):
    """Cross-competition, time-safe Poisson baseline; NOT a calibrated forecast.

    Team IDs are shared across football-data competitions. Only results before
    kickoff are considered. Sparse samples are shrunk heavily toward baselines.
    A modest league-strength adjustment is an explicit heuristic, not a rating.
    """
    try:
        kickoff = dt.datetime.fromisoformat(match['date'].replace('Z', '+00:00'))
    except (KeyError, ValueError, TypeError, AttributeError):
        return None
    valid = []
    for row in history:
        try:
            when = dt.datetime.fromisoformat(row['date'].replace('Z', '+00:00'))
            if when >= kickoff or when < kickoff - dt.timedelta(days=365):
                continue
            if not isinstance(row.get('hg'), int) or not isinstance(row.get('ag'), int):
                continue
            valid.append(row)
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    league = [r for r in valid if r['league'] == match['league']]
    if len(league) < 20:
        # A fallback is necessary for cup fixtures early in a season.
        league = [r for r in valid if r['league'] != 'Champions League']
    if len(league) < 20:
        return None
    avg_home = max(.4, sum(r['hg'] for r in league)/len(league))
    avg_away = max(.4, sum(r['ag'] for r in league)/len(league))
    hid, aid = match.get('home_id'), match.get('away_id')
    if hid is None or aid is None:
        return None
    # Use both home and away matches, including domestic games for CL clubs.
    home = sorted((r for r in valid if hid in (r['home_id'], r['away_id'])), key=lambda r:r['date'])[-20:]
    away = sorted((r for r in valid if aid in (r['home_id'], r['away_id'])), key=lambda r:r['date'])[-20:]
    if len(home) < min_samples or len(away) < min_samples:
        return None
    def side_form(records, team_id):
        transformed = []
        for r in records:
            is_home = r['home_id'] == team_id
            transformed.append({'date':r['date'], 'for':r['hg'] if is_home else r['ag'],
                                'against':r['ag'] if is_home else r['hg'],
                                'competition':r['league']})
        return transformed
    hf, af = side_form(home,hid), side_form(away,aid)
    # Home/away factors are fixed conservative priors; sparse split data is not extrapolated.
    def strength(records, baseline):
        attack = _weighted_mean(records, 'for', kickoff)
        defense = _weighted_mean(records, 'against', kickoff)
        if attack is None or defense is None:
            return 1., 1.
        # Shrink strongly to neutral: 8 equivalent prior matches.
        n = min(len(records), 20)
        return ((attack*n + baseline*8)/(n+8)/baseline,
                (defense*n + baseline*8)/(n+8)/baseline)
    baseline = (avg_home+avg_away)/2
    h_att,h_con = strength(hf,baseline)
    a_att,a_con = strength(af,baseline)
    # Explicitly limited cross-competition heuristic, not empirically fitted.
    # No adjustment without opponent ratings: cross-league results are NOT comparable.
    lh = max(.35,min(3.2,avg_home*h_att*a_con))
    la = max(.35,min(3.2,avg_away*a_att*h_con))
    ph=[poisson(i,lh) for i in range(15)]
    pa=[poisson(i,la) for i in range(15)]
    matrix=[(h,a,ph[h]*pa[a]) for h in range(15) for a in range(15)]
    total=sum(p for _,_,p in matrix)
    probs={'Home win':sum(p for h,a,p in matrix if h>a)/total,
           'Draw':sum(p for h,a,p in matrix if h==a)/total,
           'Away win':sum(p for h,a,p in matrix if h<a)/total,
           '1X (home or draw)':sum(p for h,a,p in matrix if h>=a)/total,
           'X2 (away or draw)':sum(p for h,a,p in matrix if h<=a)/total,
           'Over 1.5 goals':sum(p for h,a,p in matrix if h+a>=2)/total,
           'Over 2.5 goals':sum(p for h,a,p in matrix if h+a>=3)/total,
           'Under 3.5 goals':sum(p for h,a,p in matrix if h+a<=3)/total,
           'Both teams score':sum(p for h,a,p in matrix if h>0 and a>0)/total,
           'Home scores':1-math.exp(-lh),
           'Away scores':1-math.exp(-la)}
    domestic_h=sum(r['competition']!='Champions League' for r in hf)
    domestic_a=sum(r['competition']!='Champions League' for r in af)
    quality='Limited' if min(len(home),len(away))<6 else ('Moderate' if min(len(home),len(away))<12 else 'Broader')
    return probs,lh,la,len(home),len(away),quality,domestic_h,domestic_a

def normalize_team(name):
    name = unicodedata.normalize('NFKD', name or '')
    name = ''.join(c for c in name if not unicodedata.combining(c)).lower()
    name = re.sub(r'[^a-z0-9 ]', ' ', name)
    tokens = [t for t in name.split() if t not in {'fc','cf','sc','afc','club','football','sv','v','fk','ac','calcio','1907','1904','1899'}]
    return ' '.join(tokens)

ALIASES = {
    'bayern munchen':'bayern munich', 'fc bayern munchen':'bayern munich',
    'inter milano':'inter milan', 'internazionale milano':'inter milan',
    'paris saint germain':'psg', 'paris saint germain fc':'psg',
    'atletico de madrid':'atletico madrid', 'athletic club':'athletic bilbao',
    'manchester utd':'manchester united', 'man utd':'manchester united',
    'tottenham hotspur':'tottenham', 'borussia monchengladbach':'gladbach',
    'rb leipzig':'leipzig', 'r b leipzig':'leipzig',
    'bayer 04 leverkusen':'bayer leverkusen', 'bayer leverkusen':'bayer leverkusen',
    '1 fsv mainz 05':'mainz', 'fsv mainz 05':'mainz',
    '1 fc koln':'cologne', 'fc koln':'cologne',
    'olympique de marseille':'marseille', 'olympique lyonnais':'lyon',
    'as monaco':'monaco', 'as roma':'roma', 'ssc napoli':'napoli',
}

def canonical(name):
    n = normalize_team(name)
    return ALIASES.get(n, n)

def team_score(a,b):
    x,y=canonical(a),canonical(b)
    if x==y:return 1.0
    if not x or not y:return 0.0
    if len(x)>=5 and len(y)>=5 and (x in y or y in x):return .93
    return difflib.SequenceMatcher(None,x,y).ratio()

def odds_lookup(api_key, region='eu'):
    """Fetch h2h and 2.5 totals; store fixtures for fuzzy, kickoff-checked matching."""
    if not api_key:return {},'No odds API key: displayed probabilities are NOT bookmaker prices.'
    mapping={'PL':'soccer_epl','PD':'soccer_spain_la_liga','BL1':'soccer_germany_bundesliga','SA':'soccer_italy_serie_a','FL1':'soccer_france_ligue_one','CL':'soccer_uefa_champs_league'}
    out={}; warnings=[]; fetched=0
    for league,sport in mapping.items():
        try:
            r=requests.get(f'https://api.the-odds-api.com/v4/sports/{sport}/odds/',params={'apiKey':api_key,'regions':region,'markets':'h2h,totals','oddsFormat':'decimal'},timeout=15)
            if not r.ok:
                warnings.append(f'{league}: odds HTTP {r.status_code} — {r.text[:110]}');continue
            games=r.json()
            if not isinstance(games,list):warnings.append(f'{league}: unexpected odds response');continue
            fetched+=len(games)
            for game in games:
                gid=(league,game.get('id') or f"{game.get('home_team')}:{game.get('away_team')}:{game.get('commence_time')}")
                entry=out.setdefault(gid,{'league':league,'home':game.get('home_team',''),'away':game.get('away_team',''),'date':game.get('commence_time'),'markets':{},'by_bookmaker':{}})
                for book in game.get('bookmakers',[]):
                    for market in book.get('markets',[]):
                        for outcome in market.get('outcomes',[]):
                            label=None
                            if market.get('key')=='h2h':
                                if outcome.get('name')==game.get('home_team'):label='Home win'
                                elif outcome.get('name')==game.get('away_team'):label='Away win'
                                elif outcome.get('name')=='Draw':label='Draw'
                            elif market.get('key')=='totals' and outcome.get('point')==2.5 and outcome.get('name')=='Over':label='Over 2.5 goals'
                            odd=outcome.get('price')
                            if label and isinstance(odd,(int,float)) and odd>1:
                                entry['by_bookmaker'].setdefault(book.get('title','Unknown'),{})[label]=(float(odd),book.get('title','Unknown'))
                                prev=entry['markets'].get(label)
                                if prev is None or odd>prev[0]:entry['markets'][label]=(float(odd),book.get('title','Unknown'))
        except (requests.RequestException,ValueError) as exc:warnings.append(f'{league}: {str(exc)[:100]}')
    warnings.append(f'Odds API returned {fetched} fixtures across six competitions; only 1X2 and over 2.5 prices are requested.')
    return out,'; '.join(warnings)

def match_odds(match, odds, bookmaker=None):
    code = LEAGUES[match['league']]
    try:
        kickoff = dt.datetime.fromisoformat(
            match['date'].replace('Z', '+00:00')
        )
    except (ValueError, AttributeError):
        return {}

    best = None
    best_score = 0

    for event in odds.values():
        if not isinstance(event, dict):
            continue

        if event.get('league') != code:
            continue

        try:
            start = dt.datetime.fromisoformat(
                event['date'].replace('Z', '+00:00')
            )
        except (ValueError, TypeError, AttributeError):
            continue

        if abs((start - kickoff).total_seconds()) > 6 * 3600:
            continue

        hs = team_score(match['home'], event['home'])
        aws = team_score(match['away'], event['away'])

        if min(hs, aws) < 0.76:
            continue

        score = (hs + aws) / 2

        if score > best_score:
            best = event
            best_score = score

    return (best.get('by_bookmaker',{}).get(bookmaker,{}) if bookmaker else best['markets']) if best else {}

def candidates(fixtures,history,odds,min_samples=5,bookmaker=None):
    rows=[]
    for m in fixtures:
        result=estimate(m,history,min_samples=min_samples)
        if result is None:continue
        probs,lh,la,nh,na,quality,dh,da=result
        prices=match_odds(m,odds,bookmaker=bookmaker)
        for market,p in probs.items():
            found=prices.get(market)
            rows.append({'match_id':m['id'],'league':m['league'],'kickoff_utc':m['date'],'match':f"{m['home']} vs {m['away']}",'market':market,'probability':p,'odds':found[0] if found else None,'bookmaker':found[1] if found else None,'ev':p*found[0]-1 if found else None,'expected_goals':f'{lh:.2f}–{la:.2f}','sample':f'{nh}/{na}', 'sample_quality':quality, 'domestic_samples':f'{dh}/{da}'})
    return pd.DataFrame(rows)

def odds_diagnostics(fixtures, odds):
    """Summarize actual fixture/price matches without extra API calls."""
    from collections import Counter
    events=Counter(v.get('league') for v in odds.values() if isinstance(v,dict))
    matched=[]; unmatched=[]
    for fixture in fixtures:
        prices=match_odds(fixture,odds)
        (matched if prices else unmatched).append(fixture)
    examples=[{'competition':m['league'],'fixture':f"{m['home']} vs {m['away']}", 'kickoff_utc':m['date'], 'available_odds_events_for_league':events.get(LEAGUES[m['league']],0)} for m in unmatched[:12]]
    return {'summary':f"{len(odds)} bookmaker fixture records; {len(matched)}/{len(fixtures)} football-data fixtures matched with a bookmaker fixture. By league: "+', '.join(f'{k}: {events.get(v,0)}' for k,v in LEAGUES.items()),'examples':examples}


def build_parlays(df, require_odds=True, diversify=True, max_per_strategy=5,
                  custom_legs=None, custom_min_probability=.35, custom_target_odds=None):
    """Construct distinct-match research scenarios, with no invented prices.

    Model probabilities are uncalibrated. 'Value' means a model-vs-price
    discrepancy, NOT demonstrated profitable expected value.
    """
    if df.empty:
        return []
    data=df.copy()
    data=data[data['probability'].between(.01,.99)].copy()
    data['odds']=pd.to_numeric(data['odds'],errors='coerce')
    data.loc[data['odds']<=1,'odds']=float('nan')
    if require_odds:
        data=data[data['odds'].notna()]
    if data.empty:
        return []
    # Probability bands are soft preferences, not arbitrary exclusions.
    configs=[
        ('Conservative',2,3,.72,.99,1.5,3.0,'safety'),
        ('Balanced',3,4,.55,.82,3.0,7.0,'balance'),
        ('Aggressive · High Odds',4,6,.32,.70,8.0,25.0,'high_odds'),
        ('Aggressive · Model Value',3,5,.35,.80,5.0,18.0,'value'),
    ]
    if custom_legs:
        target=float(custom_target_odds or 5)
        configs.append(('Custom',int(custom_legs),int(custom_legs),float(custom_min_probability),.99,
                        max(1.01,target*.75),target*1.4,'custom'))
    output=[]
    for name,min_legs,max_legs,low,high,target_low,target_high,mode in configs:
        pool=data.copy()
        pool['band_distance']=pool['probability'].apply(lambda v:max(low-v,0,v-high))
        pool['price']=pool['odds'].fillna(1.0)
        pool['edge']=pool['probability']*pool['price']-1
        # Rank markets without treating model EV as a verified edge.
        if mode=='safety':
            pool['rank']=pool['probability']-pool['band_distance']*.8
        elif mode=='balance':
            pool['rank']=pool['probability']*.25+pool['price'].clip(upper=4).apply(math.log)*.25-pool['band_distance']*.8
        elif mode=='high_odds':
            pool['rank']=pool['price'].clip(upper=10).apply(math.log)*.65+pool['probability']*.3-pool['band_distance']*.65
        elif mode=='value':
            pool['rank']=pool['edge'].clip(-2,2)*.65+pool['probability']*.25-pool['band_distance']*.9
        else:
            pool['rank']=pool['probability']*.3+pool['price'].clip(upper=8).apply(math.log)*.5-pool['band_distance']*.7
        # Multiple markets per fixture may be considered, but never in the same parlay.
        pool=pool.sort_values('rank',ascending=False).groupby('match_id',sort=False).head(3)
        pool=pool.head(75)
        if pool['match_id'].nunique()<min_legs:
            continue
        records=pool.to_dict('records')
        for index,row in enumerate(records):row['_beam_index']=index
        # Beam search, bounded for responsive Streamlit performance.
        beam=[([],set(),set(),0.,0.,0.)]  # legs, IDs, leagues, log odds, log probability, ranking
        completed=[]
        for depth in range(1,max_legs+1):
            next_beam=[]
            for legs,ids,leagues,log_odds,log_prob,rank in beam:
                for row in records:
                    mid=row['match_id']
                    if mid in ids:continue
                    # Ordered selection prevents permutations and repeated combinations.
                    idx=row['_beam_index']
                    if legs and idx<=legs[-1]['_beam_index']:continue
                    new_legs=legs+[row]
                    new_leagues=leagues|{row['league']}
                    price=float(row['price'])
                    score=rank+float(row['rank'])
                    if diversify and row['league'] not in leagues and leagues:
                        score+=.07
                    state=(new_legs,ids|{mid},new_leagues,log_odds+math.log(price),log_prob+math.log(float(row['probability'])),score)
                    next_beam.append(state)
                    if depth>=min_legs:
                        completed.append(state)
            if not next_beam:break
            next_beam.sort(key=lambda x:x[5],reverse=True)
            beam=next_beam[:120]
        ranked=[]
        for legs,ids,leagues,log_odds,log_prob,rank in completed:
            priced=all(pd.notna(r['odds']) for r in legs)
            decimal=math.exp(log_odds) if priced else None
            band_penalty=sum(max(low-r['probability'],0,r['probability']-high) for r in legs)
            if decimal is not None:
                target_penalty=max(math.log(target_low)-log_odds,0,log_odds-math.log(target_high))
            else:
                target_penalty=0
            score=rank - 5.0*target_penalty - 1.5*band_penalty
            if diversify:score+=.08*len(leagues)
            # prefer 2-leg conservative, 3-leg balanced, larger high-odds slips
            if mode=='safety':score-=.15*(len(legs)-2)
            if mode=='high_odds':score+=.10*(len(legs)-min_legs)
            ranked.append((score,legs,decimal,math.exp(log_prob)))
        ranked.sort(key=lambda x:x[0],reverse=True)
        seen=set(); count=0
        for score,legs,decimal,probability in ranked:
            signature=tuple(sorted((str(r['match_id']),str(r['market'])) for r in legs))
            if signature in seen:continue
            # Avoid near-identical variants with same match set.
            match_signature=frozenset(r['match_id'] for r in legs)
            if match_signature in seen:continue
            seen.add(signature);seen.add(match_signature)
            cleaned=[{k:v for k,v in row.items() if k not in ('_beam_index','band_distance','price','edge','rank')} for row in legs]
            books={str(r['bookmaker']) for r in legs if pd.notna(r['bookmaker'])}
            output.append({'name':name,'variant':count+1,'legs':cleaned,'probability':probability,
                           'odds':decimal,'target':f'{target_low:g}–{target_high:g}×',
                           'bookmakers':len(books),'ev':None,
                           'model_edge':(probability*decimal-1) if decimal is not None else None})
            count+=1
            if count>=max_per_strategy:break
    return output
