from flask import Flask, render_template, request, jsonify
import os
import json
import re
from datetime import datetime, timedelta
from dateutil import parser as dateparser

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'smarttodo-secret-2024')

# ── NLP Parser Logic (No Database) ──────────────────────────────────────────

PRIORITY_WORDS = {
    'high':   ['urgent', 'asap', 'immediately', 'critical', 'important', 'priority', 'emergency', 'must'],
    'low':    ['sometime', 'whenever', 'eventually', 'maybe', 'if possible', 'optional', 'low priority'],
}

CATEGORY_KEYWORDS = {
    'meeting':  ['meeting', 'meet', 'conference', 'call', 'zoom', 'teams', 'standup', 'sync', 'interview', 'appointment'],
    'shopping': ['buy', 'purchase', 'shop', 'order', 'get', 'pick up', 'grocery', 'store'],
    'health':   ['doctor', 'hospital', 'gym', 'workout', 'medicine', 'dentist', 'clinic', 'exercise', 'run', 'yoga'],
    'work':     ['report', 'presentation', 'deadline', 'project', 'task', 'submit', 'review', 'email', 'office'],
    'travel':   ['flight', 'train', 'travel', 'trip', 'hotel', 'booking', 'airport', 'drive', 'bus'],
    'personal': ['birthday', 'anniversary', 'party', 'dinner', 'lunch', 'breakfast', 'family', 'friend'],
    'finance':  ['pay', 'bill', 'invoice', 'bank', 'transfer', 'tax', 'insurance', 'payment'],
    'learning': ['study', 'learn', 'read', 'course', 'class', 'practice', 'tutorial', 'book'],
}

LOCATION_PATTERNS = [
    r'\bat\s+(?:the\s+)?([A-Z][a-zA-Z\s,]+?)(?:\s+on|\s+at|\s+by|\.|,|$)',
    r'\bin\s+(?:the\s+)?([A-Z][a-zA-Z\s,]+?)(?:\s+on|\s+at|\s+by|\.|,|$)',
    r'@\s*([A-Za-z0-9\s]+)',
]

RELATIVE_DATE_MAP = {
    'today': 0, 'tonight': 0, 'tomorrow': 1, 'day after tomorrow': 2,
    'next week': 7, 'next month': 30, 'this weekend': 5,
}

WEEKDAY_MAP = {'monday':0,'tuesday':1,'wednesday':2,'thursday':3,'friday':4,'saturday':5,'sunday':6}
TIME_PATTERN = r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?\b'

def detect_priority(text):
    tl = text.lower()
    for p, words in PRIORITY_WORDS.items():
        if any(w in tl for w in words): return p
    return 'medium'

def detect_category(text):
    tl = text.lower()
    scores = {cat: sum(1 for kw in kws if kw in tl) for cat, kws in CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'general'

def extract_datetime(text):
    now = datetime.now()
    tl = text.lower()
    for phrase, days in RELATIVE_DATE_MAP.items():
        if phrase in tl: return _apply_time(now + timedelta(days=days), text)
    for day, wd in WEEKDAY_MAP.items():
        if day in tl:
            diff = (wd - now.weekday()) % 7
            if diff == 0: diff = 7
            return _apply_time(now + timedelta(days=diff), text)
    try:
        dt = dateparser.parse(text, default=now, fuzzy=True)
        if dt and dt != now: return dt
    except: pass
    return None

def _apply_time(base, text):
    m = re.search(TIME_PATTERN, text, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        mins = int(m.group(2)) if m.group(2) else 0
        ampm = (m.group(3) or '').lower()
        if ampm == 'pm' and h < 12: h += 12
        if ampm == 'am' and h == 12: h = 0
        return base.replace(hour=h, minute=mins, second=0, microsecond=0)
    return base.replace(hour=9, minute=0, second=0, microsecond=0)

def split_into_todos(paragraph):
    chunks = re.split(r'(?<=[.!?])\s+|(?:\s*[,;]\s*(?:and|also|then|after that)\s*)', paragraph)
    return [s.strip() for s in chunks if len(s.strip()) > 3]

def parse_todo(text):
    chunks = split_into_todos(text)
    results = []
    for chunk in chunks:
        results.append({
            'title': chunk[:200],
            'priority': detect_priority(chunk),
            'category': detect_category(chunk),
            'due_date': extract_datetime(chunk),
            'location': '', # Simplified for now
        })
    return results

# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/todos', methods=['POST'])
def create_todos():
    data = request.get_json()
    text = data.get('text', '').strip()
    source = data.get('source', 'nlp')

    if not text:
        return jsonify({'error': 'No text provided'}), 400

    if source == 'manual':
        parsed = [{
            'title': data.get('title', text),
            'priority': data.get('priority', 'medium'),
            'category': data.get('category', 'general'),
            'due_date': dateparser.parse(data['due_date']) if data.get('due_date') else None,
            'location': data.get('location', ''),
            'description': data.get('description', '')
        }]
    else:
        parsed = parse_todo(text)

    # Transform for Frontend (Serializing Datetime)
    timestamp = int(datetime.utcnow().timestamp() * 1000)
    final_todos = []
    for i, p in enumerate(parsed):
        final_todos.append({
            'id': timestamp + i,
            'title': p['title'],
            'priority': p['priority'],
            'category': p['category'],
            'due_date': p['due_date'].isoformat() if p['due_date'] else None,
            'location': p.get('location', ''),
            'description': p.get('description', ''),
            'completed': False,
            'created_at': datetime.utcnow().isoformat(),
            'source': source
        })

    return jsonify({'todos': final_todos, 'count': len(final_todos)}), 201

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
