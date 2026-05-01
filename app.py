from flask import Flask, render_template, request, jsonify
import os
import re
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'quantum-neuro-2026'

# ── CONSTANTS ─────────────────────────────────────────────────────────────────

WEEKDAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']

# Abbreviations including "weds", "wed", "thur", "thurs", etc.
WEEKDAY_ABBR = {
    'sun': 0, 'mon': 1, 'tue': 2, 'tues': 2,
    'wed': 3, 'weds': 3,
    'thu': 4, 'thur': 4, 'thurs': 4,
    'fri': 5, 'sat': 6,
}

MONTHS = {
    'january': 1, 'jan': 1, 'february': 2, 'feb': 2,
    'march': 3, 'mar': 3, 'april': 4, 'apr': 4,
    'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
    'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
    'october': 10, 'oct': 10, 'november': 11, 'nov': 11,
    'december': 12, 'dec': 12,
}

ORDINALS = {
    'first': '1', 'second': '2', 'third': '3', 'fourth': '4', 'fifth': '5',
    'sixth': '6', 'seventh': '7', 'eighth': '8', 'ninth': '9', 'tenth': '10',
    'eleventh': '11', 'twelfth': '12', 'thirteenth': '13', 'fourteenth': '14',
    'fifteenth': '15', 'sixteenth': '16', 'seventeenth': '17', 'eighteenth': '18',
    'nineteenth': '19', 'twentieth': '20',
    '1st': '1', '2nd': '2', '3rd': '3', '4th': '4', '5th': '5',
    '6th': '6', '7th': '7', '8th': '8', '9th': '9', '10th': '10',
    '11th': '11', '12th': '12', '13th': '13', '14th': '14', '15th': '15',
    '16th': '16', '17th': '17', '18th': '18', '19th': '19', '20th': '20',
    '21st': '21', '22nd': '22', '23rd': '23', '24th': '24', '25th': '25',
    '26th': '26', '27th': '27', '28th': '28', '29th': '29',
    '30th': '30', '31st': '31',
}

PERIOD_HOURS = {
    'early morning': 7, 'late morning': 11, 'morning': 9,
    'early afternoon': 12, 'late afternoon': 16, 'afternoon': 14,
    'late evening': 20, 'this evening': 18, 'evening': 18,
    'late night': 23, 'tonight': 20, 'night': 21,
    'midnight': 0, 'noon': 12, 'midday': 12,
    'lunchtime': 12, 'lunch': 12, 'breakfast': 8,
    'dinner': 19, 'brunch': 10, 'this morning': 9,
}

COURSE_PATTERNS = [
    re.compile(r'\bSoSe\d{4}\b', re.IGNORECASE),
    re.compile(r'\bWiSe\d{4}\b', re.IGNORECASE),
    re.compile(r'\b(Physiological|Academic English|LLM|Computing|Textwasserzeichen)\b', re.IGNORECASE),
]

TASK_START_PATTERNS = [
    re.compile(r'^[●•·▸▹►✓✗✦◆◈]\s'),
    re.compile(r'^\d+\.\s+[A-Z]'),
]

PRECISE_LOCATION_PATTERNS = [
    re.compile(r'\b(seminarraum|room|raum|saal)\s+[A-Z0-9][^\n,]{0,30}', re.IGNORECASE),
    re.compile(r'[A-Za-zäöüÄÖÜß]+str(?:asse)?\.?\s*\d+', re.IGNORECASE),
    re.compile(r'\d{5}\s+[A-Z][a-z]+'),
]


# ── NORMALISATION ─────────────────────────────────────────────────────────────

def normalize_ordinals(text):
    t = text.lower()
    for word, num in sorted(ORDINALS.items(), key=lambda x: -len(x[0])):
        t = re.sub(r'\b' + re.escape(word) + r'\b', num, t)
    return t


# ── TIME PARSING ──────────────────────────────────────────────────────────────

def parse_time_str(text):
    """
    Parse the FIRST time expression found in text.
    Handles: 18:00  18.00  17.00-18.30 (takes start)  6pm  6:30 pm  18h00
    Returns (hour, minute) or (None, None).
    """
    # 24h with colon, dot, or 'h': 18:00 / 18.00 / 18h00
    # If a range like 17.00-18.30 is present, match only the first number
    m = re.search(r'\b(\d{1,2})[:.h](\d{2})(?:\s*[-–]\s*\d{1,2}[:.h]\d{2})?\b', text)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return h, mn

    # 12h: 6pm / 6:30pm / 6:30 pm
    m = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', text, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        mn = int(m.group(2)) if m.group(2) else 0
        suffix = m.group(3).lower()
        if suffix == 'pm' and h != 12:
            h += 12
        elif suffix == 'am' and h == 12:
            h = 0
        if 0 <= h <= 23:
            return h, mn

    return None, None


def get_period_hour(text):
    t = text.lower()
    for period, hour in sorted(PERIOD_HOURS.items(), key=lambda x: -len(x[0])):
        if period in t:
            return hour, period
    return None, None


# ── DATE PARSING ──────────────────────────────────────────────────────────────

def parse_date_from_text(text, now=None):
    """
    Comprehensive date/time parser. Returns a datetime or None.

    Handles:
    - Relative: today, tomorrow, day after tomorrow, yesterday
    - Weekday abbreviations: WEDS, Wed, Wed 6 May, Weds 6 May
    - Full weekday names: next Friday, this Monday, coming Wednesday
    - Specific dates: 10th of May, May 7, Sunday 10th of May
    - "in X days/hours/minutes", next week, next month
    - Time ranges: 17.00-18.30 (uses start time)
    - Time-only expressions → today or tomorrow if past
    """
    if now is None:
        now = datetime.now()

    t = text.lower()
    t_norm = normalize_ordinals(t)
    result_date = None

    # ── 1. SIMPLE RELATIVE DAYS ────────────────────────────────────────────
    if re.search(r'day after tomorrow', t):
        result_date = now + timedelta(days=2)
    elif re.search(r'day before yesterday', t):
        result_date = now - timedelta(days=2)
    elif re.search(r'\byesterday\b', t):
        result_date = now - timedelta(days=1)
    elif re.search(r'\btoday\b|\bthis (morning|afternoon|evening|night)\b', t):
        result_date = now
    elif re.search(r'\btomorrow\b', t):
        result_date = now + timedelta(days=1)

    # ── 2. "in X days / hours / minutes" ──────────────────────────────────
    if not result_date:
        m = re.search(r'in (\d+) days?', t)
        if m:
            result_date = now + timedelta(days=int(m.group(1)))

    if not result_date:
        m = re.search(r'in (\d+) hours?', t)
        if m:
            return now + timedelta(hours=int(m.group(1)))

    if not result_date:
        m = re.search(r'in (\d+) minutes?', t)
        if m:
            return now + timedelta(minutes=int(m.group(1)))

    # ── 3. WEEKDAY ABBREVIATIONS (weds, wed, fri, mon, …) ─────────────────
    if not result_date:
        for abbr, wd_idx in sorted(WEEKDAY_ABBR.items(), key=lambda x: -len(x[0])):
            if re.search(r'\b' + abbr + r'\b', t, re.IGNORECASE):
                is_next = bool(re.search(r'\bnext\s+' + abbr + r'\b', t, re.IGNORECASE))
                current_wd = now.weekday()  # Mon=0 … Sun=6
                # Convert our Sun=0 index to Python Mon=0
                py_target = (wd_idx - 1) % 7
                diff = (py_target - current_wd) % 7
                if diff == 0 or is_next:
                    diff = 7 if diff == 0 else diff
                result_date = now + timedelta(days=diff)
                break

    # ── 4. FULL WEEKDAY NAMES ──────────────────────────────────────────────
    if not result_date:
        for i, day in enumerate(WEEKDAYS):
            if re.search(r'\b(next|coming|this)?\s*' + day + r'\b', t):
                is_next = bool(re.search(r'\bnext\s+' + day + r'\b', t))
                # Convert Sun=0 to Python Mon=0
                py_target = (i - 1) % 7
                current_wd = now.weekday()
                diff = (py_target - current_wd) % 7
                if diff == 0 or is_next:
                    diff = 7
                result_date = now + timedelta(days=diff)
                break

    # ── 5. NEXT WEEK / MONTH / END OF MONTH ───────────────────────────────
    if not result_date:
        if re.search(r'\bnext week\b', t):
            result_date = now + timedelta(weeks=1)
        elif re.search(r'in (\d+) weeks?', t):
            m = re.search(r'in (\d+) weeks?', t)
            result_date = now + timedelta(weeks=int(m.group(1)))
        elif re.search(r'\bnext month\b', t):
            result_date = now + timedelta(days=30)
        elif re.search(r'in (\d+) months?', t):
            m = re.search(r'in (\d+) months?', t)
            result_date = now + timedelta(days=30 * int(m.group(1)))
        elif re.search(r'\bend of (the )?month\b', t):
            import calendar
            last = calendar.monthrange(now.year, now.month)[1]
            result_date = now.replace(day=last)

    # ── 6. SPECIFIC DATE: "May 7", "10th of May", "WEDS 6 MAY", etc. ─────
    if not result_date:
        for mon_name, mon_num in sorted(MONTHS.items(), key=lambda x: -len(x[0])):
            # "May 7" or "May 7th"
            m = re.search(r'\b' + mon_name + r'\s+(\d{1,2})\b', t_norm)
            if m:
                day_num = int(m.group(1))
                year = now.year
                ym = re.search(r'\b(\d{4})\b', t)
                if ym:
                    year = int(ym.group(1))
                try:
                    candidate = datetime(year, mon_num, day_num, 9, 0)
                    if candidate < now and not ym:
                        candidate = candidate.replace(year=year + 1)
                    result_date = candidate
                    break
                except ValueError:
                    pass

            # "10 May", "10th of May", "WEDS 6 MAY" (day before month)
            m = re.search(r'(\d{1,2})\s+(?:of\s+)?' + mon_name + r'\b', t_norm)
            if m:
                day_num = int(m.group(1))
                year = now.year
                ym = re.search(r'\b(\d{4})\b', t)
                if ym:
                    year = int(ym.group(1))
                try:
                    candidate = datetime(year, mon_num, day_num, 9, 0)
                    if candidate < now and not ym:
                        candidate = candidate.replace(year=year + 1)
                    result_date = candidate
                    break
                except ValueError:
                    pass

    # ── 7. ISO DATE: 2026-05-07 ───────────────────────────────────────────
    if not result_date:
        m = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', t)
        if m:
            try:
                result_date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 9, 0)
            except ValueError:
                pass

    # ── 8. DD.MM.YYYY or DD/MM/YYYY ───────────────────────────────────────
    if not result_date:
        m = re.search(r'\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b', t)
        if m:
            try:
                result_date = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 9, 0)
            except ValueError:
                pass

    # ── 9. APPLY TIME TO DATE ─────────────────────────────────────────────
    if result_date:
        h, mn = parse_time_str(text)
        if h is not None:
            result_date = result_date.replace(hour=h, minute=mn, second=0, microsecond=0)
        else:
            period_h, _ = get_period_hour(text)
            if period_h is not None:
                result_date = result_date.replace(hour=period_h, minute=0, second=0, microsecond=0)

        # If computed time is in the past (today context only), push to tomorrow
        past = (result_date - now).total_seconds() < -300
        if past and 'yesterday' not in t:
            if re.search(r'\btoday\b', t) or not re.search(r'\b(tomorrow|next|coming|after)\b', t):
                result_date += timedelta(days=1)

        return result_date

    # ── 10. TIME ONLY — no date found ─────────────────────────────────────
    h, mn = parse_time_str(text)
    if h is not None:
        candidate = now.replace(hour=h, minute=mn, second=0, microsecond=0)
        if candidate < now:
            candidate += timedelta(days=1)
        return candidate

    period_h, _ = get_period_hour(text)
    if period_h is not None:
        candidate = now.replace(hour=period_h, minute=0, second=0, microsecond=0)
        if candidate < now:
            candidate += timedelta(days=1)
        return candidate

    return None


# ── CATEGORY CLASSIFIER ───────────────────────────────────────────────────────

def classify_category(text):
    t = text.lower()
    rules = [
        ('meeting', [
            'meet', 'call', 'zoom', 'teams', 'sync', 'interview', 'appointment',
            'session', 'conference', 'seminar', 'seminarraum', 'planning meeting',
            'initial meeting', 'discussion', 'weds', 'held on', 'will be held',
        ]),
        ('deadline', [
            'deadline', 'submit', 'submission', 'due', 'hand in', 'upload',
            'cloud upload', 'complete by', 'completed by', 'present',
            'presentation', 'task should', 'paper presentation', 'video',
        ]),
        ('study', [
            'exam', 'lecture', 'class', 'course', 'module', 'university',
            'moodle', 'academic', 'english', 'physiological', 'computing',
            'homework', 'assignment', 'paper', 'essay', 'thesis', 'semester',
            'sose', 'sose2026', 'uni', 'bauhausstr', 'llm', 'textwasserzeichen',
            'written exam', 'teaching classes', 'final written',
        ]),
        ('finance', [
            'bill', 'pay', 'rent', 'invoice', 'salary', 'tax', 'bank',
            'transfer', 'subscription', 'insurance',
        ]),
        ('health', [
            'doctor', 'hospital', 'clinic', 'medicine', 'prescription',
            'therapy', 'checkup', 'check-up', 'dentist', 'physio',
        ]),
        ('gym', [
            'gym', 'workout', 'exercise', 'run', 'running', 'yoga',
            'fitness', 'training', 'pilates', 'cycling', 'swim',
        ]),
        ('shopping', [
            'buy', 'get', 'shop', 'order', 'purchase', 'grocery',
            'groceries', 'supermarket', 'market', 'amazon',
        ]),
        ('travel', [
            'flight', 'trip', 'hotel', 'booking', 'bus', 'train',
            'airport', 'travel', 'journey', 'uber', 'taxi',
        ]),
        ('social', [
            'party', 'birthday', 'dinner', 'lunch', 'brunch', 'hangout',
            'catch up', 'drinks', 'celebrate', 'wedding', 'gathering',
        ]),
        ('work', [
            'report', 'email', 'send', 'project', 'review', 'develop',
            'implement', 'code', 'debug', 'deploy', 'write', 'create', 'fix',
        ]),
    ]
    for cat, keywords in rules:
        if any(kw in t for kw in keywords):
            return cat
    return 'general'


# ── LOCATION EXTRACTOR ────────────────────────────────────────────────────────

def extract_location(text):
    """
    Extract a location from text. Returns a clean string or None.
    Priority: Seminarraum > street address > room/at/in + place > online.
    """
    # Seminarraum H (015) style
    m = re.search(r'\bSEMINARRAUM\s+([A-Z]\s*\(\d+\)|[A-Z0-9]+)', text, re.IGNORECASE)
    if m:
        return 'Seminarraum ' + m.group(1).strip()

    # Street address: Bauhausstr. 11 / Bauhaus-Str 11 / Goethestr. 3
    m = re.search(r'[A-Za-zäöüÄÖÜß]+-?[Ss]tr(?:a(?:sse|ße))?\.?\s*\d+[^\n,]*', text, re.IGNORECASE)
    if m:
        return m.group(0).strip()

    # "room X", "raum X", "building X"
    m = re.search(r'\b(?:room|raum|building|gebäude|hall|saal)\s+([A-Z0-9][^\n,\.]{0,30})', text, re.IGNORECASE)
    if m:
        return m.group(0).strip()

    # "at/in PLACE" — only if place starts with uppercase (real place, not preposition artifact)
    m = re.search(r'\b(?:in|at|@)\s+([A-Z][A-Za-zäöüÄÖÜß\s\-]{3,40})', text)
    if m:
        loc = m.group(1).strip()
        # Filter out false positives like "in SEMINARRAUM" already handled
        if len(loc) > 3 and not any(x in loc.lower() for x in ['the', 'which', 'that', 'this']):
            return loc

    # Online platforms
    if re.search(r'\b(zoom|teams|online|virtual|remote)\b', text, re.IGNORECASE):
        return 'Online'

    return None


def get_maps_url(location):
    """
    Return a Google Maps search URL if the location looks like a mappable address.
    Only for street addresses — not for room numbers or online.
    """
    if not location:
        return None
    # Street pattern
    if re.search(r'[A-Za-zäöüÄÖÜß]+str(?:asse|aße)?\.?\s*\d+', location, re.IGNORECASE):
        query = location + ', Weimar, Germany'
        return f'https://www.google.com/maps/search/?api=1&query={query}'
    return None


# ── SMART SPLIT ───────────────────────────────────────────────────────────────

def smart_split(text):
    """
    Split complex pasted text (Moodle announcements, multi-course notes) into
    individual task chunks. Handles course blocks, bullets, and inline sentences.
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    filtered = []
    for line in lines:
        # Drop bare URLs
        if re.match(r'^https?://', line):
            continue
        # Drop "From <url>" lines
        if re.match(r'^from\s*<?https?', line, re.IGNORECASE):
            continue
        if len(line) < 4:
            continue
        filtered.append(line)

    chunks = []
    current = ''

    for i, line in enumerate(filtered):
        # Bullet within a line — split on the bullet
        if any(b in line for b in ['●', '•']):
            if current.strip():
                chunks.append(current.strip())
                current = ''
            parts = re.split(r'[●•]', line)
            parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
            for p in parts[:-1]:
                chunks.append(p)
            current = parts[-1] if parts else ''
            continue

        # New course block detected on its own line — start fresh chunk
        is_new_course = any(p.search(line) for p in COURSE_PATTERNS) and len(current) > 20
        is_task_start = any(p.match(line) for p in TASK_START_PATTERNS)

        if is_new_course or (is_task_start and current.strip()):
            if current.strip():
                chunks.append(current.strip())
            current = line
        else:
            current = (current + ' ' + line).strip() if current else line

    if current.strip():
        chunks.append(current.strip())

    # Post-process: if any chunk is very long, try to split on strong sentence breaks
    result = []
    for chunk in chunks:
        if len(chunk) > 500:
            # Split on ". " followed by a capital letter that looks like a new sentence
            parts = re.split(r'(?<=\.)\s+(?=[A-Z][A-Z\s]{5,})', chunk)
            result.extend([p.strip() for p in parts if len(p.strip()) > 4])
        else:
            result.append(chunk)

    return [r for r in result if len(r) > 4]


# ── TITLE CLEANUP ─────────────────────────────────────────────────────────────

def clean_title(raw):
    t = raw
    t = re.sub(r'https?://\S+', '', t)
    t = re.sub(r'from\s*<https?://[^>]+>', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s{2,}', ' ', t)
    t = re.sub(r'^[●•·▸▹►\s]+', '', t)
    t = t.strip()
    if t:
        t = t[0].upper() + t[1:]
    if len(t) > 180:
        t = t[:177] + '…'
    return t


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
        maps_url = get_maps_url(loc)
        title = clean_title(clean)

        if not title or len(title) < 3:
            continue

        task_id = int(now.timestamp() * 1000) + len(results)
        while task_id in seen_ids:
            task_id += 1
        seen_ids.add(task_id)

        results.append({
            'id': task_id,
            'title': title,
            'due_date': dt.isoformat() if dt else None,
            'category': cat,
            'location': loc,
            'maps_url': maps_url,
            'reminder': True,
            'reminderOffset': 15,
            'completed': False,
            'reminded': False,
            'source': 'nlp',
            'priority': 'normal',
            'notes': None,
        })

    return jsonify(results)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
