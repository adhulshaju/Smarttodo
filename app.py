from flask import Flask, render_template, request, jsonify
import os
import re
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'quantum-neuro-2026'

# ── ULTRA NLP ENGINE ─────────────────────────────────────────────────────────

WEEKDAYS = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']
MONTHS = {
    'january':1,'jan':1,'february':2,'feb':2,'march':3,'mar':3,
    'april':4,'apr':4,'may':5,'june':6,'jun':6,'july':7,'jul':7,
    'august':8,'aug':8,'september':9,'sep':9,'sept':9,
    'october':10,'oct':10,'november':11,'nov':11,'december':12,'dec':12
}
ORDINALS = {
    'first':'1','second':'2','third':'3','fourth':'4','fifth':'5','sixth':'6',
    'seventh':'7','eighth':'8','ninth':'9','tenth':'10','eleventh':'11',
    'twelfth':'12','thirteenth':'13','fourteenth':'14','fifteenth':'15',
    'sixteenth':'16','seventeenth':'17','eighteenth':'18','nineteenth':'19',
    'twentieth':'20','twenty-first':'21','twenty-second':'22','twenty-third':'23',
    'twenty-fourth':'24','twenty-fifth':'25','twenty-sixth':'26',
    'twenty-seventh':'27','twenty-eighth':'28','twenty-ninth':'29','thirtieth':'30',
    'thirty-first':'31','1st':'1','2nd':'2','3rd':'3','4th':'4','5th':'5',
    '6th':'6','7th':'7','8th':'8','9th':'9','10th':'10','11th':'11','12th':'12',
    '13th':'13','14th':'14','15th':'15','16th':'16','17th':'17','18th':'18',
    '19th':'19','20th':'20','21st':'21','22nd':'22','23rd':'23','24th':'24',
    '25th':'25','26th':'26','27th':'27','28th':'28','29th':'29','30th':'30','31st':'31'
}

PERIOD_HOURS = {
    'morning': 9, 'early morning': 7, 'late morning': 11,
    'afternoon': 14, 'early afternoon': 12, 'late afternoon': 16,
    'evening': 18, 'late evening': 20,
    'night': 21, 'late night': 23, 'midnight': 0,
    'noon': 12, 'midday': 12, 'lunchtime': 12, 'lunch': 12,
    'breakfast': 8, 'dinner': 19, 'brunch': 10,
    'tonight': 20, 'this evening': 18, 'this morning': 9,
}


def normalize_ordinals(text):
    """Replace ordinal words with numbers."""
    t = text.lower()
    for word, num in sorted(ORDINALS.items(), key=lambda x: -len(x[0])):
        t = t.replace(word, num)
    return t


def parse_time_str(text):
    """Parse time expressions like '18:00', '6pm', '6:30 pm', '18.00'."""
    text = text.strip()
    # 24h like 18:00 or 18.00
    m = re.search(r'\b(\d{1,2})[:.h](\d{2})\b', text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return h, mn

    # 12h like 6pm, 6:30pm, 6:30 pm
    m = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', text, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        mn = int(m.group(2)) if m.group(2) else 0
        suffix = m.group(3).lower()
        if suffix == 'pm' and h != 12:
            h += 12
        elif suffix == 'am' and h == 12:
            h = 0
        return h, mn

    return None, None


def get_period_hour(text):
    """Find period of day in text and return hour."""
    t = text.lower()
    for period, hour in sorted(PERIOD_HOURS.items(), key=lambda x: -len(x[0])):
        if period in t:
            return hour, period
    return None, None


def parse_date_from_text(text, now=None):
    """
    Comprehensive date/time parser that handles:
    - Relative: today, tomorrow, day after tomorrow, day before yesterday
    - Weekdays: next Friday, this Monday, coming Wednesday
    - Ordinals: 10th of May, May 7th, Sunday 10th of May
    - Relative weeks/months: next week, in 2 weeks, next month
    - "in X days/hours/minutes"
    - Specific datetime combos: "Sunday, 10th of May, 18:00"
    - Time-only: "at 5pm" → today or tomorrow if past
    Returns: datetime or None
    """
    if now is None:
        now = datetime.now()

    t = text.lower()
    t_norm = normalize_ordinals(t)

    result_date = None

    # ── 1. EXACT PATTERNS ──────────────────────────────────────────────────

    # "day after tomorrow" / "the day after tomorrow"
    if re.search(r'day after tomorrow', t):
        result_date = now + timedelta(days=2)

    # "day before yesterday"
    elif re.search(r'day before yesterday', t):
        result_date = now - timedelta(days=2)

    # "yesterday"
    elif re.search(r'\byesterday\b', t):
        result_date = now - timedelta(days=1)

    # "today" / "this afternoon" etc
    elif re.search(r'\btoday\b|\bthis (morning|afternoon|evening|night)\b', t):
        result_date = now

    # "tomorrow"
    elif re.search(r'\btomorrow\b', t):
        result_date = now + timedelta(days=1)

    # "in X days"
    else:
        m = re.search(r'in (\d+) days?', t)
        if m:
            result_date = now + timedelta(days=int(m.group(1)))

    if not result_date:
        # "in X hours"
        m = re.search(r'in (\d+) hours?', t)
        if m:
            return now + timedelta(hours=int(m.group(1)))

    if not result_date:
        # "in X minutes"
        m = re.search(r'in (\d+) minutes?', t)
        if m:
            return now + timedelta(minutes=int(m.group(1)))

    # ── 2. NEXT / THIS / COMING + WEEKDAY ─────────────────────────────────
    if not result_date:
        for day in WEEKDAYS:
            if re.search(rf'\b(next|coming|this)\s+{day}\b', t) or \
               re.search(rf'\b{day}\b', t):
                target_wd = WEEKDAYS.index(day)
                current_wd = now.weekday()
                is_next = bool(re.search(rf'\bnext\s+{day}\b', t))
                diff = (target_wd - current_wd) % 7
                if diff == 0 and is_next:
                    diff = 7
                elif diff == 0:
                    diff = 7  # "Friday" when today is Friday → next week
                result_date = now + timedelta(days=diff)
                break

    # ── 3. NEXT WEEK / NEXT MONTH ─────────────────────────────────────────
    if not result_date:
        if re.search(r'\bnext week\b', t):
            result_date = now + timedelta(weeks=1)
        elif re.search(r'\bin (\d+) weeks?\b', t):
            m = re.search(r'in (\d+) weeks?', t)
            result_date = now + timedelta(weeks=int(m.group(1)))
        elif re.search(r'\bnext month\b', t):
            result_date = now + timedelta(days=30)
        elif re.search(r'\bin (\d+) months?\b', t):
            m = re.search(r'in (\d+) months?', t)
            result_date = now + timedelta(days=30*int(m.group(1)))
        elif re.search(r'\bend of (the )?month\b', t):
            import calendar
            last = calendar.monthrange(now.year, now.month)[1]
            result_date = now.replace(day=last)
        elif re.search(r'\bend of (the )?semester\b|\bend of (the )?year\b', t):
            result_date = now.replace(month=12, day=31)

    # ── 4. SPECIFIC DATE: "May 7", "7 May", "Sunday 10th of May", "May 7th 2026" ──
    if not result_date:
        # Pattern: month name + day number (e.g. "May 7", "May 7th")
        for mon_name, mon_num in sorted(MONTHS.items(), key=lambda x: -len(x[0])):
            m = re.search(rf'\b{mon_name}\s+(\d{{1,2}})\b', t_norm)
            if m:
                day_num = int(m.group(1))
                year = now.year
                candidate = datetime(year, mon_num, day_num, now.hour, now.minute)
                if candidate < now:
                    candidate = candidate.replace(year=year+1)
                result_date = candidate
                break
            # "7 May" or "10th of May"
            m = re.search(rf'(\d{{1,2}})\s+(?:of\s+)?{mon_name}\b', t_norm)
            if m:
                day_num = int(m.group(1))
                year = now.year
                # Check for explicit year
                ym = re.search(rf'{mon_name}.*?(\d{{4}})', t_norm)
                if ym:
                    year = int(ym.group(1))
                try:
                    candidate = datetime(year, mon_num, day_num, 9, 0)
                    if candidate < now and not ym:
                        candidate = candidate.replace(year=year+1)
                    result_date = candidate
                    break
                except ValueError:
                    pass

    # ── 5. NUMERIC DATE: "07.05.2026", "2026-05-07", "05/07/2026" ─────────
    if not result_date:
        # ISO: 2026-05-07
        m = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', t)
        if m:
            try:
                result_date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 9, 0)
            except ValueError:
                pass

    if not result_date:
        # DD.MM.YYYY or DD/MM/YYYY
        m = re.search(r'\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b', t)
        if m:
            try:
                result_date = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 9, 0)
            except ValueError:
                pass

    # ── 6. APPLY TIME ─────────────────────────────────────────────────────
    if result_date:
        # Try explicit time first (18:00, 5pm, etc.)
        h, mn = parse_time_str(text)
        if h is not None:
            result_date = result_date.replace(hour=h, minute=mn, second=0, microsecond=0)
        else:
            # Try period of day
            period_h, period_name = get_period_hour(text)
            if period_h is not None:
                result_date = result_date.replace(hour=period_h, minute=0, second=0, microsecond=0)

        # Past-correction: if it's today and time already passed, push to tomorrow
        if (result_date - now).total_seconds() < -300 and 'yesterday' not in t:
            if re.search(r'\btoday\b', t) or (not re.search(r'\b(tomorrow|next|coming|after)\b', t)):
                result_date += timedelta(days=1)

        return result_date

    # ── 7. TIME ONLY (no date): "at 5pm", "at 18:00" ─────────────────────
    h, mn = parse_time_str(text)
    if h is not None:
        candidate = now.replace(hour=h, minute=mn, second=0, microsecond=0)
        if candidate < now:
            candidate += timedelta(days=1)
        return candidate

    # Period only (e.g. "tonight", "this morning")
    period_h, period_name = get_period_hour(text)
    if period_h is not None:
        candidate = now.replace(hour=period_h, minute=0, second=0, microsecond=0)
        if candidate < now:
            candidate += timedelta(days=1)
        return candidate

    return None


def classify_category(text):
    """Expanded keyword-based category classifier."""
    t = text.lower()
    rules = [
        ('meeting', ['meet','call','zoom','teams','sync','interview','appointment',
                     'session','conference','seminar','seminarraum','planning meeting',
                     'initial meeting','discussion']),
        ('deadline', ['deadline','submit','submission','due','hand in','upload','cloud upload',
                      'complete by','completed by','present','presentation','task should']),
        ('study', ['exam','lecture','class','course','module','university','moodle','academic',
                   'english','physiological','computing','homework','assignment','paper',
                   'essay','thesis','semester','sose','sose2026','uni','bauhausstr']),
        ('finance', ['bill','pay','rent','invoice','salary','tax','bank','transfer',
                     'subscription','insurance']),
        ('health', ['doctor','hospital','clinic','medicine','prescription','therapy',
                    'checkup','check-up','dentist','physio']),
        ('gym', ['gym','workout','exercise','run','running','yoga','fitness','training',
                 'pilates','cycling','swim']),
        ('shopping', ['buy','get','shop','order','purchase','grocery','groceries',
                      'supermarket','market','amazon']),
        ('travel', ['flight','trip','hotel','booking','bus','train','airport','travel',
                    'journey','uber','taxi','drive to','pick up']),
        ('social', ['party','birthday','dinner','lunch','brunch','hangout','catch up',
                    'drinks','celebrate','wedding','gathering']),
        ('work', ['report','email','send','submit','presentation','project','review',
                  'develop','implement','code','debug','deploy','write','create','fix']),
    ]
    for cat, keywords in rules:
        if any(kw in t for kw in keywords):
            return cat
    return 'general'


def extract_location(text):
    """Try to extract a location hint from text."""
    # Look for explicit location keywords
    patterns = [
        r'(?:in|at|@|room|raum|seminarraum|building|gebäude|hall|saal)\s+([A-Z][^\.,\n]{2,40})',
        r'(?:bauhausstr\.?\s*\d+)',
        r'(?:zoom|teams|online|virtual|remote)',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def smart_split(text):
    """
    Intelligently split complex text into individual task chunks.
    Handles: newlines, bullet points, semicolons, 'and then', etc.
    Also handles structured moodle/academic text.
    """
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Split on clear task separators
    # Strategy: split on newlines that start a new logical task,
    # on bullet points, on strong conjunctions between different actions
    lines = []

    # First, split by newline groups
    raw_lines = [l.strip() for l in text.split('\n') if l.strip()]

    for line in raw_lines:
        # Skip pure URL lines
        if re.match(r'^https?://', line):
            continue
        # Skip "From <url>" lines
        if re.match(r'^from\s*<https?', line, re.IGNORECASE):
            continue
        # Skip very short lines (likely headers/labels already absorbed)
        if len(line) < 5:
            continue
        # Split on " and " between clauses (only if both sides are substantial)
        sub = re.split(r'\s+and\s+(?=[a-z])', line, flags=re.IGNORECASE)
        lines.extend([s.strip() for s in sub if len(s.strip()) > 4])

    # Merge very short orphan lines with previous
    merged = []
    for l in lines:
        if merged and len(l) < 15 and not any(kw in l.lower() for kw in ['may','june','july','aug','sep']):
            merged[-1] += ' ' + l
        else:
            merged.append(l)

    return [m for m in merged if len(m) > 4]


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/parse', methods=['POST'])
def parse_nlp():
    data = request.get_json()
    text = data.get('text', '')
    now = datetime.now()

    chunks = smart_split(text)
    results = []
    seen_ids = set()

    for chunk in chunks:
        clean = chunk.strip()
        if len(clean) < 3:
            continue

        dt = parse_date_from_text(clean, now)
        cat = classify_category(clean)
        loc = extract_location(clean)

        # Title cleanup: remove URL artifacts, shorten if too long
        title = clean
        title = re.sub(r'from\s*<https?://[^>]+>', '', title, flags=re.IGNORECASE).strip()
        title = re.sub(r'https?://\S+', '', title).strip()
        title = re.sub(r'\s{2,}', ' ', title)
        # Capitalize first letter
        title = title[0].upper() + title[1:] if title else title
        # Truncate if very long
        if len(title) > 200:
            title = title[:197] + '…'

        task_id = int(now.timestamp() * 1000) + len(results)
        if task_id in seen_ids:
            task_id += 1
        seen_ids.add(task_id)

        results.append({
            'id': task_id,
            'title': title,
            'due_date': dt.isoformat() if dt else None,
            'category': cat,
            'location': loc,
            'reminder': True,
            'reminderOffset': 15,
            'completed': False,
            'reminded': False,
            'source': 'nlp',
            'priority': 'normal'
        })

    return jsonify(results)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
