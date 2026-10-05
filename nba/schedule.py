"""Provider-neutral slate dates and explicit team identity joins."""
from zoneinfo import ZoneInfo
from .model import instant

SLATE_TZ='America/New_York'

def slate_day(timestamp):
    return instant(timestamp).astimezone(ZoneInfo(SLATE_TZ)).date().isoformat()

def normalize_espn(payload,roster,date):
    # Full team names from the live NBA roster avoid ESPN/NBA abbreviation mismatches.
    names={}
    abbreviations={}
    for p in roster:
        entry=(str(p['team_id']),p['team'])
        name=p.get('team_name','').strip().casefold()
        if name:names.setdefault(name,set()).add(entry)
        abbreviations.setdefault(p['team'].upper(),set()).add(entry)
    games=[]
    for event in payload.get('events',[]):
        if not event.get('date') or slate_day(event['date'])!=date:continue
        competitions=event.get('competitions',[])
        if not competitions:raise ValueError('Schedule event has no competition details')
        competition=competitions[0]
        matched={}
        for competitor in competition.get('competitors',[]):
            team=competitor['team']
            matches=names.get(team.get('displayName','').strip().casefold(),set())
            if not matches:matches=abbreviations.get(team.get('abbreviation','').upper(),set())
            if len(matches)!=1:raise ValueError('Cannot uniquely map schedule team '+team.get('displayName','unknown')+' to NBA roster')
            matched[competitor['homeAway']]=next(iter(matches))
        if set(matched)!={'home','away'}:raise ValueError('Schedule is missing home or away team')
        season_type=event.get('season',{}).get('type')
        phase={1:'Preseason',2:'Regular Season',3:'Playoffs'}.get(season_type,'Unknown')
        status=event.get('status',competition.get('status',{})).get('type',{})
        games.append({'game_id':'espn:'+str(event['id']),'game_time':instant(event['date']).isoformat(),
            'home_id':matched['home'][0],'home':matched['home'][1],
            'away_id':matched['away'][0],'away':matched['away'][1],
            'season_type':phase,'game_status':status.get('description','Unknown'),
            'completed':bool(status.get('completed',False)), 'source':'ESPN scoreboard; NBA roster team mapping'})
    return games
