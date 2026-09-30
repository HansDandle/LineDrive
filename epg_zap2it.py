from bs4 import BeautifulSoup
import re
import requests
from datetime import datetime, timedelta
import pytz
from config_manager import get_config

# Gracenote's listings API rejects requests that don't look like a browser (HTTP 403)
GRACENOTE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    'Accept': 'application/json',
    'Referer': 'https://tvlistings.gracenote.com/',
}

def parse_postal_code(code):
    """('USA', '10001') for a US ZIP, ('CAN', 'M5V3L9') for a Canadian postal code (Gracenote
    wants it without the space), or None for anything else"""
    code = re.sub(r'\s+', '', str(code or '')).upper()
    if re.fullmatch(r'\d{5}', code):
        return 'USA', code
    if re.fullmatch(r'[A-Z]\d[A-Z]\d[A-Z]\d', code):
        return 'CAN', code
    return None

def split_postal_codes(value):
    """epg.zip_code can hold several codes ("L2E 6S4, 14201") for antennas that reach another
    market Gracenote lists separately"""
    return [c.strip() for c in re.split(r'[,;]', str(value or '')) if c.strip()]

def ota_lineup_id(code):
    """Gracenote's over-the-air lineup for a postal code, e.g. USA-OTA10001-DEFAULT"""
    country, code = parse_postal_code(code)
    return f"{country}-OTA{code}-DEFAULT"

def _local_tz():
    """Timezone for guide times: epg.timezone if set, else None, which means this machine's
    local zone (astimezone(None)); that matches the scheduler, which runs on the system clock"""
    name = get_config().get_epg_config()['timezone']
    if not name:
        return None
    try:
        return pytz.timezone(name)
    except pytz.UnknownTimeZoneError:
        print(f"Unknown epg.timezone '{name}'; using this machine's time zone")
        return None

def detect_headend_id(zip_code, country='USA'):
    """Detect headend ID for a given zip code by querying Gracenote"""
    try:
        # First, try to get lineup information for this zip code
        lookup_url = "https://tvlistings.gracenote.com/api/lineups"
        headers = GRACENOTE_HEADERS
        
        params = {
            'country': country,
            'postalCode': zip_code
        }
        
        response = requests.get(lookup_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Look for the primary headend ID (usually the first/default one)
        if data and isinstance(data, list) and len(data) > 0:
            # Try to find an over-the-air or cable headend
            for lineup in data:
                if isinstance(lineup, dict) and 'headendId' in lineup:
                    headend_id = lineup['headendId']
                    lineup_name = lineup.get('name', 'Unknown')
                    print(f"Detected headend ID '{headend_id}' for zip {zip_code} ({lineup_name})")
                    return headend_id
        
        print(f"Warning: Could not detect headend ID for zip code {zip_code}")
        return ""
        
    except Exception as e:
        print(f"Error detecting headend ID for zip {zip_code}: {e}")
        return ""

def fetch_gracenote_epg(days=7, zip_code=None, headend_id=None):
    """Fetch EPG data from Gracenote API for specified location and multiple days"""
    try:
        # Get configuration
        config = get_config()
        epg_config = config.get_epg_config()
        
        # Use provided parameters or fall back to configuration
        if zip_code is None:
            zip_code = (split_postal_codes(epg_config['zip_code']) or [''])[0]
        if headend_id is None:
            headend_id = epg_config['headend_id']
        parsed = parse_postal_code(zip_code)
        if not parsed:
            print(f"Gracenote: '{zip_code}' isn't a US ZIP or Canadian postal code")
            return []
        country, zip_code = parsed
            
        # Auto-detect headend ID if not provided
        if not headend_id:
            print(f"Auto-detecting headend ID for zip code {zip_code}...")
            headend_id = detect_headend_id(zip_code, country)
            if headend_id:
                # Save the detected headend ID to config for future use
                config.set('epg', 'headend_id', headend_id)
                config.save_config()
                print(f"Saved headend ID '{headend_id}' to configuration")
        
        # Gracenote only accepts real lineup IDs (e.g. USA-OTA10001-DEFAULT); older setups
        # stored made-up "NY10001:X" values, so fall back to the over-the-air lineup
        if not (headend_id or '').startswith(f'{country}-'):
            headend_id = ota_lineup_id(zip_code)

        print(f"Fetching EPG data for zip code {zip_code}, lineup ID: {headend_id}")
        
        # Use the exact parameters from your working URL
        base_url = "https://tvlistings.gracenote.com/api/grid"
        headers = GRACENOTE_HEADERS
        
        # Fetch data for multiple days to catch recurring shows
        all_results = []
        
        # Generate timestamps for better coverage throughout each day
        # Start from current time and cover multiple days with different time periods
        base_date = datetime.now()
        current_time = datetime.now()
        day_timestamps = []
        
        for day_offset in range(days):
            current_date = base_date + timedelta(days=day_offset)
            
            # For each day, fetch multiple time periods to ensure full coverage
            # Four back-to-back 6-hour windows cover the full day
            time_periods = [
                (0, "12AM"),
                (6, "6AM"),
                (12, "12PM"),
                (18, "6PM")
            ]
            
            for hour, label in time_periods:
                time_slot = current_date.replace(hour=hour, minute=0, second=0, microsecond=0)
                time_slot_end = time_slot + timedelta(hours=6)  # Each window covers 6 hours
                
                # Skip time periods only if the ENTIRE window has already passed
                if day_offset == 0 and time_slot_end <= current_time:
                    continue  # Skip only if the 6-hour window has completely passed
                
                day_timestamps.append(int(time_slot.timestamp()))
        
        # Fetch data for each timestamp period
        for i, timestamp in enumerate(day_timestamps):
            target_date = datetime.fromtimestamp(timestamp)
            
            params = {
                'lineupId': headend_id,
                'timespan': '6',  # 6 hours coverage per fetch
                'headendId': 'lineupId',
                'country': country,
                'timezone': '',  # Leave empty for auto-detection
                'device': '-',
                'postalCode': zip_code,
                'isOverride': 'true',
                'time': str(timestamp),  # Use calculated timestamps
                'pref': '32,256',
                'userId': '-',
                'aid': 'orbebb',
                'languagecode': 'en-us'
            }
            
            print(f"Fetching EPG data for {target_date.strftime('%Y-%m-%d %H:%M')} (6-hour block)...")
            
            try:
                r = requests.get(base_url, params=params, headers=headers, timeout=15)
                r.raise_for_status()
                data = r.json()
                
                # Process this time period's data
                period_results = parse_gracenote_data(data, target_date.strftime('%Y-%m-%d'))
                all_results.extend(period_results)
                
            except Exception as e:
                print(f"  Error fetching {target_date.strftime('%Y-%m-%d %H:%M')}: {e}")
                continue
        
        print(f"Gracenote API: Found {len(all_results)} programs across {len(day_timestamps)} time periods ({days} days)")
        
        # Only use real API data - no fallback data
        return all_results
        
    except Exception as e:
        print(f"Gracenote API error: {e}")
        import traceback
        traceback.print_exc()
        return []  # Return empty list instead of fallback data

def search_epg_for_show(show_name, days=7):
    """Search EPG data for any show name and return all matching episodes with smart sports matching"""
    print(f"Searching EPG for show: '{show_name}' over next {days} days...")
    
    # Get all EPG data for the specified number of days
    all_epg_data = fetch_zap2it_epg(days)
    
    # Search for matching shows with improved logic
    matching_episodes = []
    show_name_lower = show_name.lower()
    
    # Extract key terms for smarter matching
    show_words = [word.strip() for word in show_name_lower.split()]
    
    # Sports-specific logic with comprehensive team names
    sports_terms = ['football', 'game', 'basketball', 'baseball', 'soccer', 'hockey', 'tennis', 'golf', 'match', 'vs', 'at']
    
    # Comprehensive college team mappings (team name -> possible variations)
    college_teams = {
        'utah': ['utah', 'utes'],
        'west virginia': ['west virginia', 'wvu', 'mountaineers'],
        'texas': ['texas', 'ut', 'longhorns', 'hook em'],
        'oklahoma': ['oklahoma', 'ou', 'sooners'],
        'alabama': ['alabama', 'bama', 'crimson tide'],
        'georgia': ['georgia', 'uga', 'bulldogs', 'dawgs'],
        'michigan': ['michigan', 'wolverines'],
        'ohio state': ['ohio state', 'osu', 'buckeyes'],
        'notre dame': ['notre dame', 'fighting irish'],
        'clemson': ['clemson', 'tigers'],
        'florida': ['florida', 'gators'],
        'lsu': ['lsu', 'tigers'],
        'tennessee': ['tennessee', 'vols', 'volunteers'],
        'auburn': ['auburn', 'tigers'],
        'penn state': ['penn state', 'nittany lions'],
        'wisconsin': ['wisconsin', 'badgers'],
        'oregon': ['oregon', 'ducks'],
        'stanford': ['stanford', 'cardinal'],
        'usc': ['usc', 'trojans', 'southern cal'],
        'ucla': ['ucla', 'bruins'],
        'washington': ['washington', 'huskies'],
        'miami': ['miami', 'hurricanes'],
        'florida state': ['florida state', 'fsu', 'seminoles'],
        'virginia tech': ['virginia tech', 'vt', 'hokies'],
        'nc state': ['nc state', 'wolfpack'],
        'duke': ['duke', 'blue devils'],
        'north carolina': ['north carolina', 'unc', 'tar heels'],
        'kansas': ['kansas', 'jayhawks'],
        'nebraska': ['nebraska', 'cornhuskers'],
        'iowa': ['iowa', 'hawkeyes'],
        'minnesota': ['minnesota', 'gophers'],
        'purdue': ['purdue', 'boilermakers'],
        'illinois': ['illinois', 'fighting illini'],
        'northwestern': ['northwestern', 'wildcats'],
        'indiana': ['indiana', 'hoosiers'],
        'maryland': ['maryland', 'terrapins'],
        'rutgers': ['rutgers', 'scarlet knights'],
        'michigan state': ['michigan state', 'msu', 'spartans'],
        'baylor': ['baylor', 'bears'],
        'tcu': ['tcu', 'horned frogs'],
        'texas tech': ['texas tech', 'red raiders'],
        'oklahoma state': ['oklahoma state', 'cowboys'],
        'kansas state': ['kansas state', 'wildcats'],
        'iowa state': ['iowa state', 'cyclones'],
        'west virginia': ['west virginia', 'wvu', 'mountaineers']
    }

    # NFL team mappings (team name -> possible variations / abbreviations)
    nfl_teams = {
        'dallas cowboys': ['dallas cowboys', 'cowboys', 'dallas', 'dal'],
        'new york giants': ['new york giants', 'giants', 'nyg'],
        'philadelphia eagles': ['philadelphia eagles', 'eagles', 'phi'],
        'washington commanders': ['washington commanders', 'commanders', 'washington', 'was'],
        'san francisco 49ers': ['san francisco 49ers', '49ers', 'niners', 'sf', 'sfo'],
        'seattle seahawks': ['seattle seahawks', 'seahawks', 'sea'],
        'los angeles rams': ['los angeles rams', 'rams', 'la rams', 'lar'],
        'arizona cardinals': ['arizona cardinals', 'cardinals', 'cards', 'ari'],
        'green bay packers': ['green bay packers', 'packers', 'gb'],
        'chicago bears': ['chicago bears', 'bears', 'chi'],
        'detroit lions': ['detroit lions', 'lions', 'det'],
        'minnesota vikings': ['minnesota vikings', 'vikings', 'min'],
        'tampa bay buccaneers': ['tampa bay buccaneers', 'buccaneers', 'bucs', 'tb'],
        'new orleans saints': ['new orleans saints', 'saints', 'no', 'nor'],
        'atlanta falcons': ['atlanta falcons', 'falcons', 'atl'],
        'carolina panthers': ['carolina panthers', 'panthers', 'carolina', 'car'],
        'kansas city chiefs': ['kansas city chiefs', 'chiefs', 'kc'],
        'denver broncos': ['denver broncos', 'broncos', 'den'],
        'las vegas raiders': ['las vegas raiders', 'raiders', 'lv', 'lar'],
        'los angeles chargers': ['los angeles chargers', 'chargers', 'la chargers', 'lac'],
        'buffalo bills': ['buffalo bills', 'bills', 'buf'],
        'miami dolphins': ['miami dolphins', 'dolphins', 'mia'],
        'new england patriots': ['new england patriots', 'patriots', 'pats', 'ne', 'nep'],
        'new york jets': ['new york jets', 'jets', 'nyj'],
        'baltimore ravens': ['baltimore ravens', 'ravens', 'bal'],
        'pittsburgh steelers': ['pittsburgh steelers', 'steelers', 'pit'],
        'cleveland browns': ['cleveland browns', 'browns', 'cle'],
        'cincinnati bengals': ['cincinnati bengals', 'bengals', 'cin'],
        'houston texans': ['houston texans', 'texans', 'hou'],
        'indianapolis colts': ['indianapolis colts', 'colts', 'ind'],
        'jacksonville jaguars': ['jacksonville jaguars', 'jaguars', 'jags', 'jax'],
        'tennessee titans': ['tennessee titans', 'titans', 'ten']
    }

    # Merge NFL first to prioritize pro teams in ambiguous nickname cases (e.g., Cowboys)
    team_mappings = {**nfl_teams, **college_teams}

    # Flatten team variations for easier searching
    all_team_variations = []
    for variations in team_mappings.values():
        all_team_variations.extend(variations)
    
    is_sports_query = any(term in show_name_lower for term in sports_terms)
    is_team_query = any(team in show_name_lower for team in all_team_variations)
    
    for program in all_epg_data:
        title = program.get('title', '').lower()
        description = program.get('description', '').lower()
        genre = program.get('genre', '').lower()
        
        # Scoring system for match quality
        match_score = 0
        
        # Exact title match (highest score)
        if show_name_lower == title:
            match_score = 100
        
        # Partial title matches
        elif show_name_lower in title or title in show_name_lower:
            match_score = 80
            
        # Word-based matching
        else:
            title_words = title.split()
            matching_words = sum(1 for word in show_words if any(word in title_word for title_word in title_words))
            if matching_words > 0:
                match_score = (matching_words / len(show_words)) * 60
        
        # Enhanced description matching
        description_words = description.split() if description else []
        desc_matching_words = sum(1 for word in show_words if any(word in desc_word for desc_word in description_words))
        if desc_matching_words > 0:
            match_score += (desc_matching_words / len(show_words)) * 50
        
        # Enhanced sports and team matching
        if is_sports_query or is_team_query:
            # Look for sports genre
            if 'sport' in genre:
                match_score += 20
            
            # DETECT preview/analysis shows vs actual games
            preview_show_indicators = [
                'gameday', 'game day', 'preview', 'analysis', 'wrap up', 'wrap-up', 
                'post game', 'postgame', 'highlights', 'recap', 'roundup', 'tonight',
                'weekly', 'show', 'talk', 'discussion'
            ]
            
            is_preview_show = any(indicator in title.lower() or indicator in description.lower() 
                                for indicator in preview_show_indicators)
            
            # PRIORITIZE actual games over preview shows
            actual_game_indicators = [
                'vs', 'at', ' v ', 'versus'  # These indicate actual matchups
            ]
            
            is_actual_game = any(indicator in title.lower() or indicator in description.lower() 
                               for indicator in actual_game_indicators)
            
            # Enhanced team matching - unified college + NFL
            for team_name, variations in team_mappings.items():
                # Check if any variation of this team is mentioned in the search query
                query_mentions_team = any(variation in show_name_lower for variation in variations)

                if not query_mentions_team:
                    continue

                # Check if this team appears in the program title or description
                program_mentions_team = any(variation in title or variation in description for variation in variations)

                if not program_mentions_team:
                    continue

                is_nfl_team = team_name in nfl_teams
                is_college_team = not is_nfl_team

                # Additional NFL context bonus if generic listing
                nfl_context = ('nfl' in title or 'nfl' in description or 'nfl football' in title or 'nfl football' in description)

                if is_actual_game:
                    if is_nfl_team:
                        # Higher score for actual NFL game
                        match_score += 120
                        if nfl_context:
                            match_score += 15
                        # Extra disambiguation: Cowboys - ensure Dallas context outranks Oklahoma State
                        if 'cowboys' in variations and 'dallas' in (title + ' ' + description):
                            match_score += 10
                    else:
                        match_score += 100  # College actual game
                elif is_preview_show:
                    match_score += 5  # cap applied later
                else:
                    # Medium content (features, specials) - give slight differentiation
                    if is_nfl_team:
                        base = 55
                        if nfl_context:
                            base += 10
                        match_score += base
                    else:
                        match_score += 50
                # Mark program with team match metadata for downstream logic (UI, suppression rules)
                program['team_match'] = True
                program.setdefault('matched_teams', []).append(team_name)
                # Break after first team match to avoid double-counting (NFL prioritized earlier in mapping)
                break
            
            # Generic sports content matching
            if 'football' in show_name_lower:
                if 'football' in title.lower() and 'college' in title.lower():
                    if is_actual_game:
                        match_score += 75   # High score for actual college football games
                    elif is_preview_show:
                        match_score += 2    # Minimal score for preview shows
                    else:
                        match_score += 25   # Medium score for other football content
                        
                if 'football' in description.lower():
                    if is_actual_game:
                        match_score += 50
                    elif is_preview_show:
                        match_score += 2    # Minimal score for preview shows
                    else:
                        match_score += 20
            
            # Apply FINAL PENALTY for preview shows - this ensures they stay below 50
            if is_preview_show:
                match_score = min(match_score, 40)  # Cap preview shows at 40 max
            
            # Generic game/match terms
            if any(term in show_name_lower for term in ['game', 'match', 'vs']):
                if any(term in title for term in ['vs', 'at', 'game']):
                    match_score += 15
        
        # Accept matches with score > 30
        if match_score > 30:
            program['match_score'] = match_score
            matching_episodes.append(program)
            print(f"  Found: {program.get('title')} on {program.get('channel')} at {program.get('time')} on {program.get('date')} (score: {match_score:.1f})")
    
    # Sort by match score (best matches first)
    matching_episodes.sort(key=lambda x: x.get('match_score', 0), reverse=True)
    
    print(f"Found {len(matching_episodes)} episodes of '{show_name}'")
    return matching_episodes
    
def analyze_show_pattern(episodes):
    """Analyze episodes to determine if show is daily, weekly, or one-time"""
    if len(episodes) < 2:
        return "one-time", episodes
    
    # Group episodes by day of week and time
    from collections import defaultdict
    by_day_time = defaultdict(list)
    
    for episode in episodes:
        try:
            date_obj = datetime.strptime(episode['date'], '%Y-%m-%d')
            day_of_week = date_obj.weekday()  # Monday=0, Sunday=6
            time_slot = episode.get('time', 'Unknown')
            key = f"{day_of_week}_{time_slot}"
            by_day_time[key].append(episode)
        except:
            continue
    
    # Analyze patterns
    weekday_slots = []  # Monday-Friday
    weekend_slots = []  # Saturday-Sunday
    
    for key, eps in by_day_time.items():
        if len(eps) >= 2:  # Show appears multiple times in this slot
            day_num = int(key.split('_')[0])
            if day_num < 5:  # Monday-Friday
                weekday_slots.extend(eps)
            else:  # Saturday-Sunday
                weekend_slots.extend(eps)
    
    # Determine pattern
    if len(weekday_slots) >= 4:  # Appears on multiple weekdays
        pattern = "daily-weekdays"
        return pattern, weekday_slots
    elif len(weekend_slots) >= 2:  # Weekend show
        pattern = "weekly-weekend"
        return pattern, weekend_slots
    elif len(episodes) >= 3:  # Multiple episodes but not clearly daily
        pattern = "weekly"
        return pattern, episodes
    else:
        pattern = "limited-series"
        return pattern, episodes

def group_episodes_by_series(episodes):
    """Group episodes into recording series based on channel and time patterns"""
    from collections import defaultdict
    series_groups = defaultdict(list)
    
    for episode in episodes:
        # Create a key based on channel, day pattern, and time
        try:
            date_obj = datetime.strptime(episode['date'], '%Y-%m-%d')
            day_of_week = date_obj.weekday()
            
            # Group weekdays together, weekends separately
            if day_of_week < 5:
                day_group = "weekdays"
            else:
                day_group = "weekend"
            
            channel = episode.get('channel_number', episode.get('channel', 'Unknown'))
            time_slot = episode.get('time', 'Unknown')
            
            series_key = f"{channel}_{day_group}_{time_slot}"
            series_groups[series_key].append(episode)
        except:
            # If date parsing fails, put in a general group
            series_groups['general'].append(episode)
    
    return dict(series_groups)

def parse_gracenote_data(data, target_date):
    """Parse Gracenote API response data for a specific date"""
    results = []
    
    # Parse the JSON response - use all available channels
    # Note: Channel filtering should be done based on user's actual HDHomeRun lineup
    
    if 'channels' in data:
        for channel in data['channels']:
            # Get channel information from the API response
            call_sign = channel.get('callSign', '')
            affiliate_name = channel.get('affiliateName', '')
            channel_no = channel.get('channelNo', channel.get('number', 'N/A'))
            channel_name = channel.get('name', call_sign or 'Unknown')
            
            # Process all channels (no filtering by specific market)
            
            # Create channel display name
            if call_sign and affiliate_name and affiliate_name.upper() != 'NULL':
                channel_display = f"{call_sign} {affiliate_name} ({channel_no})"
            elif call_sign:
                channel_display = f"{call_sign} ({channel_no})"
            else:
                channel_display = f"Channel {channel_no}"
            
            if 'events' in channel:
                for event in channel['events']:  # Get all events for this channel
                    program = event.get('program', {})
                    title = program.get('title', 'Unknown')
                    
                    # Skip generic or empty titles
                    if title in ['Unknown', '', 'TBA', 'To Be Announced']:
                        continue
                    
                    # Extract additional metadata
                    # Gracenote grid field names (older names kept as fallbacks)
                    episode_title = program.get('episodeTitle') or ''
                    season_number = program.get('season') or program.get('seasonNumber') or ''
                    episode_number = program.get('episode') or program.get('episodeNumber') or ''
                    original_air_date = program.get('originalAirDate') or ''
                    description = program.get('shortDesc') or program.get('description') or ''
                    # Categories arrive as e.g. ["filter-sports"] -> "Sports"
                    genre = ', '.join(f.replace('filter-', '').title() for f in (event.get('filter') or []) if f)
                    rating = event.get('rating') or program.get('rating') or ''
                    year = program.get('releaseYear') or program.get('year') or ''
                    flags = [f for f in (event.get('flag') or []) if f]  # e.g. ["New", "Live"]
                    duration = event.get('duration', '')
                    
                    # Build episode identifier for filename
                    episode_id = ""
                    if season_number and episode_number:
                        episode_id = f"S{season_number:0>2}E{episode_number:0>2}"
                    elif episode_number:
                        episode_id = f"E{episode_number:0>2}"
                    
                    # Format air date for filename
                    air_date_formatted = ""
                    if original_air_date:
                        try:
                            # Try parsing various date formats
                            if 'T' in original_air_date:
                                dt = datetime.fromisoformat(original_air_date.replace('Z', '+00:00'))
                            else:
                                dt = datetime.strptime(original_air_date, '%Y-%m-%d')
                            air_date_formatted = dt.strftime('%Y-%m-%d')
                        except:
                            air_date_formatted = original_air_date
                    
                    # Parse start time with proper timezone handling
                    start_time = event.get('startTime', '')
                    time_str = "TBD"
                    date_str = target_date  # Use the target date passed in
                    
                    if start_time:
                        try:
                            # Handle ISO format from API
                            if 'T' in start_time:
                                # Parse the ISO timestamp
                                if start_time.endswith('Z'):
                                    # UTC timestamp
                                    dt_utc = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                                else:
                                    dt_utc = datetime.fromisoformat(start_time)
                                
                                # Convert to the guide time zone (or this machine's)
                                central_tz = _local_tz()
                                if dt_utc.tzinfo is None:
                                    # Assume UTC if no timezone info
                                    dt_utc = dt_utc.replace(tzinfo=pytz.UTC)
                                
                                dt_central = dt_utc.astimezone(central_tz)
                                
                                # Commented out verbose timezone logging
                                # print(f"Timezone conversion: {start_time} -> {dt_central.strftime('%I:%M %p')} Central Time")
                                
                            elif start_time.isdigit():
                                # Unix timestamp - convert to the guide time zone
                                dt_utc = datetime.fromtimestamp(int(start_time), tz=pytz.UTC)
                                central_tz = _local_tz()
                                dt_central = dt_utc.astimezone(central_tz)
                            else:
                                # Try other formats
                                dt_central = datetime.fromisoformat(start_time)
                                if dt_central.tzinfo is None and _local_tz() is not None:
                                    # A time without a zone is taken as local guide time
                                    dt_central = _local_tz().localize(dt_central)
                            
                            time_str = dt_central.strftime('%I:%M %p')
                            date_str = dt_central.strftime('%Y-%m-%d')
                            
                            # Determine period based on Central Time
                            hour = dt_central.hour
                            if 6 <= hour < 12:
                                period = 'Morning'
                            elif 12 <= hour < 18:
                                period = 'Afternoon'
                            else:
                                period = 'Evening'
                        
                        except Exception as time_error:
                            print(f"Time parsing error for {start_time}: {time_error}")
                            # Fallback time parsing
                            import re
                            time_match = re.search(r'(\d{1,2}:\d{2})', start_time)
                            if time_match:
                                time_str = time_match.group(1)
                                # Try to determine AM/PM
                                hour = int(time_str.split(':')[0])
                                if hour >= 6 and hour <= 11:
                                    time_str += ' AM'
                                    period = 'Morning'
                                elif hour >= 12 and hour <= 17:
                                    time_str += ' PM'
                                    period = 'Afternoon'
                                else:
                                    time_str += ' PM'
                                    period = 'Evening'
                            else:
                                period = 'Current'
                    else:
                        period = 'Current'
                    
                    results.append({
                        'channel': channel_display,
                        'title': title,
                        'time': time_str,
                        'date': date_str,
                        'period': period,
                        'is_local': True,  # Local channels
                        'call_sign': call_sign,
                        'channel_number': channel_no,
                        # Enhanced metadata
                        'episode_title': episode_title,
                        'season_number': season_number,
                        'episode_number': episode_number,
                        'episode_id': episode_id,
                        'original_air_date': air_date_formatted,
                        'description': description,
                        'genre': genre,
                        'rating': rating,
                        'year': year,
                        'flags': flags,
                        'duration': duration
                    })
    
    return results

# FALLBACK DATA DISABLED - Using only real API data
# def get_fallback_epg_data():
#     """Fallback EPG data disabled - using only real Gracenote API data"""
#     return []

def lineup_stations(code):
    """[(channel number, call sign)] in a code's over-the-air lineup right now (an hour of the grid)"""
    import time
    country, postal = parse_postal_code(code)
    params = {'lineupId': ota_lineup_id(code), 'headendId': 'lineupId', 'device': '-', 'timespan': '1',
              'country': country, 'postalCode': postal, 'isOverride': 'true', 'time': str(int(time.time())),
              'pref': '16,128', 'userId': '-', 'aid': 'orbebb', 'languagecode': 'en-us', 'timezone': ''}
    r = requests.get('https://tvlistings.gracenote.com/api/grid', params=params, timeout=15, headers=GRACENOTE_HEADERS)
    if not r.ok:
        return []
    return [(str(c.get('channelNo', '')), c.get('callSign', '')) for c in r.json().get('channels', [])]

def merge_lineups(lineups):
    """Listings from several codes' lineups, each station once: where two lineups carry the same
    station (channel number + call sign), the earlier code's listings are kept"""
    merged, seen = [], set()
    for progs in lineups:
        stations = {(str(p.get('channel_number')), p.get('call_sign')) for p in progs}
        fresh = stations - seen
        merged.extend(p for p in progs if (str(p.get('channel_number')), p.get('call_sign')) in fresh)
        seen |= stations
    return merged

def fetch_zap2it_epg(days=7):
    """Gracenote listings for every configured ZIP/postal code, merged (the first code wins)"""
    codes = [c for c in split_postal_codes(get_config().get_epg_config()['zip_code']) if parse_postal_code(c)]
    lineups = []
    for i, code in enumerate(codes):
        # Only the first code uses (and may save) epg.headend_id; the rest use their over-the-air lineup
        lineups.append(fetch_gracenote_epg(days, zip_code=code, headend_id=None if i == 0 else ota_lineup_id(code)))
    return merge_lineups(lineups)