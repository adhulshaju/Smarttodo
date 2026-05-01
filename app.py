from flask import Flask, render_template, request, jsonify
import os
import re
from datetime import datetime, timedelta
from dateutil import parser as dateparser

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'smarttodo-ultra-pro-2024')

# ── ADVANCED LEXICON ────────────────────────────────────────────────────────

# Categories with weighted intent
INTENTS = {
    'meeting':  ['call', 'zoom', 'meet', 'interview', 'sync', 'discuss', 'appointment', 'session'],
    'shopping': ['buy', 'get', 'purchase', 'pick up', 'order', 'grocery', 'target', 'amazon'],
    'finance':  ['pay', 'bill', 'rent', 'invoice', 'transfer', 'tax', 'subscription', 'cost'],
    'health':   ['gym', 'workout', 'doctor', 'dentist', 'medicine', 'run', 'yoga', 'exercise'],
    'work':     ['submit', 'email', 'report', 'presentation', 'deadline', 'client', 'review'],
}

# ── STRONGER NLP LOGIC ───────────────────────────────────────────────────────

def clean_text(text):
    # Remove filler words that confuse parsers
    fillers = ['i need to', 'remind me to', 'i want to', 'please', 'can you']
    t = text.lower()
    for f in fillers:
        t = t.replace(f, '')
    return t.strip()

def extract_entities(text):
    # Detect Location (Words following 'at', 'in', 'near')
    loc_match = re.search(r'\b(?:at|in|near|@)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text)
    location = loc_match.group(1) if loc_match else ""
    
    # Detect Category based on intent keywords
    category = 'general'
    max_score = 0
    tl = text.lower()
    for cat, keywords in INTENTS.items():
        score = sum(2 if kw in tl else 0 for kw in keywords)
        if score > max_score:
            max_score = score
            category = cat
            
    return category, location

def parse_advanced_date(text):
    now = datetime.now()
    tl = text.lower()
    
    # Hand-coded overrides for tricky relative dates
    if 'tonight' in tl:
        return now.replace(hour=20, minute=0, second=0)
    if 'morning' in tl:
        return now.replace(hour=9, minute=0, second=0) + (timedelta(days=1) if 'tomorrow' in tl else timedelta(0))
    
    try:
        # dateutil fuzzy handles: "Next Friday", "In 3 days", "May 5th"
        dt = dateparser.parse(text, default=now, fuzzy=True)
        # Verify it's actually a detected date and not just 'now'
        if dt.replace(microsecond=0) != now.replace(microsecond=0):
            return dt
    except:
        pass
    return None

def split_smart(text):
    # Splits on punctuation AND logical conjunctions (and, then, also) 
    # but ONLY if followed by a verb-like word
    logic_split = r'\s+(?:and|then|also|plus)\s+(?=[a-z]{3,})'
    punct_split = r'[.!?;]\s+'
    chunks = re.split(f'{logic_split}|{punct_split}', text, flags=re.IGNORECASE)
    return [c.strip() for c in chunks if len(c.strip()) > 4]

# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/todos', methods=['POST'])
def create_todos():
    data = request.get_json()
    raw_text = data.get('text', '').strip()
    if not raw_text: return jsonify({'error': 'No text'}), 400

    chunks = split_smart(raw_text)
    final_tasks = []
    base_id = int(datetime.utcnow().timestamp() * 1000)

    for i, chunk in enumerate(chunks):
        cleaned = clean_text(chunk)
        cat, loc = extract_entities(chunk) # Use original chunk for Proper Noun detection
        due = parse_advanced_date(chunk)
        
        final_tasks.append({
            'id': base_id + i,
            'title': cleaned.capitalize(),
            'priority': 'high' if any(x in chunk.lower() for x in ['urgent', 'asap', '!']) else 'medium',
            'category': cat,
            'location': loc,
            'due_date': due.isoformat() if due else None,
            'completed': False,
            'created_at': datetime.utcnow().isoformat(),
            'source': 'nlp'
        })

    return jsonify({'todos': final_tasks}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
