"""API-Football v3 adapter. Only public match data; API key stays server-side."""
import datetime as dt
import requests

BASE = 'https://v3.football.api-sports.io'
LEAGUE_IDS = {'Premier League':39, 'La Liga':140, 'Bundesliga':78,
              'Serie A':135, 'Ligue 1':61, 'Champions League':2}
FINISHED = {'FT','AET','PEN'}
UPCOMING = {'NS','TBD'}

class APIError(Exception):
    pass

def request(key, path, params=None):
    if not key:
        raise APIError('Enter your API-Football key.')
    try:
        response = requests.get(BASE + path, headers={'x-apisports-key': key},
                                params=params or {}, timeout=22)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise APIError(f'API-Football request failed: {str(exc)[:150]}') from exc
    errors = payload.get('errors')
    if errors:
        raise APIError(f'API-Football: {str(errors)[:180]}')
    paging = payload.get('paging') or {}
    if int(paging.get('total',1)) > 1:
        raise APIError('Response is paginated; refusing to use incomplete fixture data.')
    remaining = response.headers.get('x-ratelimit-requests-remaining')
    return payload.get('response', []), remaining

def _row(item, league):
    fix = item.get('fixture') or {}
    teams = item.get('teams') or {}
    home = teams.get('home') or {}
    away = teams.get('away') or {}
    goals = item.get('goals') or {}
    status = (fix.get('status') or {}).get('short','')
    date = fix.get('date')
    if not (date and home.get('id') and away.get('id')):
        return None
    row = {'id':fix.get('id'),'league':league,'date':date,
           'home':home.get('name'),'away':away.get('name'),
           'home_id':home.get('id'),'away_id':away.get('id'),
           'status':status, 'api_football_id':fix.get('id')}
    if status in FINISHED and isinstance(goals.get('home'),int) and isinstance(goals.get('away'),int):
        row.update(hg=goals['home'],ag=goals['away'])
    return row

def fixtures_and_history(key, days=3, selected=None, today=None):
    """Fetch current + previous seasons per league (up to 12 calls for 6 leagues).

    Each API response is a whole season. No cross-provider ID mixing.
    Results are filtered to 365-day lookback and next N days.
    """
    today = today or dt.datetime.now(dt.timezone.utc).date()
    start = today - dt.timedelta(days=365)
    end = today + dt.timedelta(days=days)
    fixtures, history, warnings, remaining = [], [], [], None
    names = [name for name in (selected or LEAGUE_IDS) if name in LEAGUE_IDS]
    for name in names:
        league_id = LEAGUE_IDS[name]
        season = today.year if today.month >= 7 else today.year-1
        for year in (season-1,season):
            try:
                records, remaining = request(key,'/fixtures',{'league':league_id,'season':year})
            except APIError as exc:
                warnings.append(f'{name} {year}: {exc}')
                continue
            for item in records:
                row = _row(item,name)
                if row is None:
                    continue
                try:
                    day = dt.datetime.fromisoformat(row['date'].replace('Z','+00:00')).date()
                except ValueError:
                    continue
                if start <= day < today and 'hg' in row:
                    history.append(row)
                elif today <= day <= end and row['status'] in UPCOMING:
                    fixtures.append(row)
    fixtures = list({r['id']:r for r in fixtures}.values())
    history = list({r['id']:r for r in history}.values())
    return fixtures, history, '; '.join(warnings), remaining

def preview(key, fixture_id):
    """Fetch provider's pre-match prediction; display separately from our model."""
    rows, remaining = request(key, '/predictions', {'fixture':int(fixture_id)})
    if not rows:
        return None, remaining
    item = rows[0]
    prediction = item.get('predictions') or {}
    return {'advice':prediction.get('advice'),
            'percent':prediction.get('percent') or {},
            'winner':(prediction.get('winner') or {}).get('name'),
            'under_over':prediction.get('under_over'),
            'goals':item.get('teams') or {}}, remaining
