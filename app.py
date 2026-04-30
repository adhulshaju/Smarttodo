from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import re
import json
import os
from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'smarttodo-secret-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///todos.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ── Models ──────────────────────────────────────────────────────────────────

class Todo(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(300), nullable=False)
    description= db.Column(db.Text, default='')
    topic      = db.Column(db.String(100), default='')
    location   = db.Column(db.String(200), default='')
    due_date   = db.Column(db.DateTime, nullable=True)
    priority   = db.Column(db.String(20), default='medium')   # low / medium / high
    category   = db.Column(db.String(100), default='general')
    completed  = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    source     = db.Column(db.String(20), default='nlp')       # nlp / manual
    tags       = db.Column(db.Text, default='[]')              # JSON list

    def to_dict(self):
        return {
            'id':          self.id,
            'title':       self.title,
            'description': self.description,
            'topic':       self.topic,
            'location':    self.location,
            'due_date':    self.due_date.isoformat() if self.due_date else None,
            'priority':    self.priority,
            'category':    self.category,
            'completed':   self.completed,
            'created_at':  self.created_at.isoformat(),
            'source':      self.source,
            'tags':        json.loads(self.tags or '[]'),
        }

# ── NLP Parser ───────────────────────────────────────────────────────────────

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
    r'\b(?:room|office|building|floor|hall|center|park|street|avenue|road|lane|drive|blvd)\b[^,.]*',
    r'@\s*([A-Za-z0-9\s]+)',
]

RELATIVE_DATE_MAP = {
    'today':       0, 'tonight':     0,
    'tomorrow':    1, 'day after tomorrow': 2,
    'next week':   7, 'next month':  30,
    'this weekend':5,
}

WEEKDAY_MAP = {
    'monday':0,'tuesday':1,'wednesday':2,'thursday':3,
    'friday':4,'saturday':5,'sunday':6,
}

TIME_PATTERN = r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?\b'

def detect_priority(text: str) -> str:
    tl = text.lower()
    for p, words in PRIORITY_WORDS.items():
        if any(w in tl for w in words):
            return p
    return 'medium'

def detect_category(text: str) -> str:
    tl = text.lower()
    scores = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for kw in kws if kw in tl)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'general'

def extract_tags(text: str) -> list:
    tags = []
    tl = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in tl and kw not in tags:
                tags.append(kw)
    return tags[:5]

def extract_location(text: str) -> str:
    for pat in LOCATION_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            loc = m.group(0) if m.lastindex is None else m.group(1)
            loc = loc.strip().strip(',').strip('.')
            if 3 < len(loc) < 60:
                return loc
    return ''

def extract_datetime(text: str) -> datetime | None:
    now = datetime.now()
    tl  = text.lower()

    # relative keywords
    for phrase, days in RELATIVE_DATE_MAP.items():
        if phrase in tl:
            base = now + timedelta(days=days)
            return _apply_time(base, text)

    # weekday names
    for day, wd in WEEKDAY_MAP.items():
        if day in tl:
            diff = (wd - now.weekday()) % 7
            if diff == 0: diff = 7
            base = now + timedelta(days=diff)
            return _apply_time(base, text)

    # explicit date patterns
    date_patterns = [
        r'\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b',
        r'\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(\d{2,4})?\b',
        r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{2,4})?\b',
    ]
    for pat in date_patterns:
        m = re.search(pat, tl)
        if m:
            try:
                dt = dateparser.parse(m.group(0), default=now)
                if dt:
                    return _apply_time(dt, text)
            except Exception:
                pass

    # loose dateutil parse on the whole string
    try:
        dt = dateparser.parse(text, default=now, fuzzy=True)
        if dt and dt != now:
            return dt
    except Exception:
        pass

    return None

def _apply_time(base: datetime, text: str) -> datetime:
    m = re.search(TIME_PATTERN, text, re.IGNORECASE)
    if m:
        h = int(m.group(1))
        mins = int(m.group(2)) if m.group(2) else 0
        ampm = (m.group(3) or '').lower()
        if ampm == 'pm' and h < 12: h += 12
        if ampm == 'am' and h == 12: h = 0
        return base.replace(hour=h, minute=mins, second=0, microsecond=0)
    return base.replace(hour=9, minute=0, second=0, microsecond=0)

def extract_topic(text: str) -> str:
    """Guess a short topic label."""
    cat = detect_category(text)
    for kw, cats in CATEGORY_KEYWORDS.items():
        if cat == kw:
            return cat.capitalize()
    return 'General'

# ── Split a paragraph into multiple todo sentences ──────────────────────────

SENTENCE_SPLITTERS = re.compile(
    r'(?<=[.!?])\s+|(?:\s*[,;]\s*(?:and|also|then|after that|later|additionally)\s*)|'
    r'(?:\s+and\s+(?:also\s+)?(?:i\s+need|i\s+have|i\s+must|remind|schedule|book|call|send|submit|pick|buy|get|meet))',
    re.IGNORECASE,
)

TODO_TRIGGER = re.compile(
    r'\b(need to|have to|must|should|will|going to|plan to|want to|remind|schedule|book|call|'
    r'send|submit|pick up|buy|get|meet|visit|attend|prepare|review|complete|finish|check|'
    r'update|create|write|read|study|exercise|pay|register|apply|email|message)\b',
    re.IGNORECASE,
)

def split_into_todos(paragraph: str) -> list[str]:
    """Split a complex paragraph into individual task strings."""
    raw = [s.strip() for s in SENTENCE_SPLITTERS.split(paragraph) if s and s.strip()]
    if not raw:
        raw = [paragraph]

    # further split on "and I need/must/will ..."
    final = []
    for chunk in raw:
        sub = re.split(r'\s+and\s+(?=(?:i\s+)?(?:need|must|have|will|should|plan|want|also))', chunk, flags=re.IGNORECASE)
        final.extend([s.strip() for s in sub if s.strip()])

    # keep only segments that look like tasks
    result = [s for s in final if TODO_TRIGGER.search(s) or len(s.split()) <= 8]
    return result if result else [paragraph]

def parse_todo(text: str, source: str = 'nlp') -> list[dict]:
    chunks = split_into_todos(text.strip())
    todos = []
    for chunk in chunks:
        if len(chunk) < 3:
            continue
        title    = chunk[:200]
        priority = detect_priority(chunk)
        category = detect_category(chunk)
        location = extract_location(chunk)
        due_date = extract_datetime(chunk)
        topic    = extract_topic(chunk)
        tags     = extract_tags(chunk)
        todos.append({
            'title':    title,
            'topic':    topic,
            'location': location,
            'due_date': due_date,
            'priority': priority,
            'category': category,
            'source':   source,
            'tags':     tags,
        })
    return todos

# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/todos', methods=['GET'])
def get_todos():
    sort_by  = request.args.get('sort', 'upcoming')   # upcoming | created | priority
    show     = request.args.get('show', 'all')          # all | active | completed
    category = request.args.get('category', '')

    q = Todo.query
    if show == 'active':    q = q.filter_by(completed=False)
    if show == 'completed': q = q.filter_by(completed=True)
    if category:            q = q.filter_by(category=category)

    if sort_by == 'upcoming':
        todos = q.order_by(
            db.case((Todo.due_date == None, 1), else_=0),
            Todo.due_date.asc(),
            Todo.created_at.desc(),
        ).all()
    elif sort_by == 'priority':
        order = db.case({'high':0,'medium':1,'low':2}, value=Todo.priority)
        todos = q.order_by(order, Todo.created_at.desc()).all()
    else:
        todos = q.order_by(Todo.created_at.desc()).all()

    return jsonify([t.to_dict() for t in todos])

@app.route('/api/todos', methods=['POST'])
def create_todos():
    data = request.get_json()
    text = data.get('text', '').strip()
    source = data.get('source', 'nlp')

    if not text:
        return jsonify({'error': 'No text provided'}), 400

    if source == 'manual':
        parsed = [{
            'title':       data.get('title', text),
            'topic':       data.get('topic', ''),
            'location':    data.get('location', ''),
            'due_date':    dateparser.parse(data['due_date']) if data.get('due_date') else None,
            'priority':    data.get('priority', 'medium'),
            'category':    data.get('category', 'general'),
            'source':      'manual',
            'tags':        [],
            'description': data.get('description', ''),
        }]
    else:
        parsed = parse_todo(text)

    created = []
    for p in parsed:
        todo = Todo(
            title       = p['title'],
            description = p.get('description', ''),
            topic       = p.get('topic', ''),
            location    = p.get('location', ''),
            due_date    = p.get('due_date'),
            priority    = p.get('priority', 'medium'),
            category    = p.get('category', 'general'),
            source      = p.get('source', 'nlp'),
            tags        = json.dumps(p.get('tags', [])),
        )
        db.session.add(todo)
        db.session.flush()
        created.append(todo.to_dict())
    db.session.commit()
    return jsonify({'todos': created, 'count': len(created)}), 201

@app.route('/api/todos/<int:todo_id>', methods=['PUT'])
def update_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    data = request.get_json()
    for field in ['title','description','topic','location','priority','category','completed']:
        if field in data:
            setattr(todo, field, data[field])
    if 'due_date' in data:
        todo.due_date = dateparser.parse(data['due_date']) if data['due_date'] else None
    if 'tags' in data:
        todo.tags = json.dumps(data['tags'])
    db.session.commit()
    return jsonify(todo.to_dict())

@app.route('/api/todos/<int:todo_id>', methods=['DELETE'])
def delete_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    db.session.delete(todo)
    db.session.commit()
    return jsonify({'deleted': True})

@app.route('/api/todos/bulk-delete', methods=['POST'])
def bulk_delete():
    data = request.get_json()
    ids  = data.get('ids', [])
    Todo.query.filter(Todo.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'deleted': len(ids)})

@app.route('/api/categories', methods=['GET'])
def get_categories():
    cats = db.session.query(Todo.category, db.func.count(Todo.id))\
               .group_by(Todo.category).all()
    return jsonify([{'name': c, 'count': n} for c, n in cats])

@app.route('/api/stats', methods=['GET'])
def get_stats():
    total     = Todo.query.count()
    completed = Todo.query.filter_by(completed=True).count()
    pending   = total - completed
    overdue   = Todo.query.filter(
        Todo.due_date < datetime.utcnow(),
        Todo.completed == False
    ).count()
    return jsonify({'total': total, 'completed': completed,
                    'pending': pending, 'overdue': overdue})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
