from flask import Flask, render_template, request, jsonify
import os
import re
from datetime import datetime, timedelta
from dateutil import parser as dateparser

app = Flask(__name__)
app.config['SECRET_KEY'] = 'quantum-neuro-2026'

# ── STRONGER NLP ENGINE ──────────────────────────────────────────────────────

def parse_neuro_logic(text):
    now = datetime.now()
    t = text.lower()
    
    # 1. Advanced Scenario-Based Date Shifts
    target_date = now
    if 'day after tomorrow' in t:
        target_date = now + timedelta(days=2)
    elif 'tomorrow' in t:
        target_date = now + timedelta(days=1)
    elif 'next week' in t:
        target_date = now + timedelta(days=7)
    elif 'next month' in t:
        target_date = now + timedelta(days=30)
    
    # 2. Intent-Based Time Buckets (Scenarios)
    # Mapping human periods to specific 24h hours
    hour_bucket = None
    if 'morning' in t: hour_bucket = 8
    elif 'afternoon' in t: hour_bucket = 14
    elif 'evening' in t: hour_bucket = 18
    elif 'night' in t: hour_bucket = 21
    elif 'tonight' in t: 
        hour_bucket = 20
        target_date = now

    try:
        # Fuzzy parse handles "May 7", "Friday", "in 3 hours"
        dt = dateparser.parse(text, default=target_date, fuzzy=True)
        
        # Scenario: If a bucket was mentioned but no specific time (e.g., "Friday night")
        # override the default time with the scenario bucket.
        if ':' not in t and not re.search(r'\d+\s*(am|pm)', t):
            if hour_bucket is not None:
                dt = dt.replace(hour=hour_bucket, minute=0, second=0, microsecond=0)
        
        # Scenario: Automatic Past-Correction
        # If "5:00 PM" is entered at 6:00 PM, shift it to tomorrow.
        if dt < now and (now - dt).total_seconds() < 86400:
            dt = dt + timedelta(days=1)
            
        return dt
    except:
        return None

# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/parse', methods=['POST'])
def parse_nlp():
    data = request.get_json()
    text = data.get('text', '')
    
    # Advanced Splitter: Logical conjunctions and punctuation
    chunks = re.split(r' and | then | also |\. |; ', text, flags=re.IGNORECASE)
    results = []
    
    for chunk in chunks:
        clean_chunk = chunk.strip()
        if len(clean_chunk) < 3: continue
        
        dt = parse_neuro_logic(clean_chunk)
        
        # Expanded Scenario Categories
        cat_logic = {
            'meeting': ['meet', 'call', 'zoom', 'sync', 'interview', 'appointment'],
            'shopping': ['buy', 'get', 'shop', 'order', 'purchase', 'grocery'],
            'finance': ['bill', 'pay', 'rent', 'invoice', 'salary', 'tax'],
            'health': ['gym', 'workout', 'doctor', 'medicine', 'exercise', 'clinic'],
            'work': ['report', 'email', 'submit', 'presentation', 'deadline'],
            'travel': ['flight', 'trip', 'hotel', 'booking', 'bus', 'train']
        }
        
        category = 'general'
        for cat, keywords in cat_logic.items():
            if any(w in clean_chunk.lower() for w in keywords):
                category = cat
                break

        results.append({
            'id': int(datetime.utcnow().timestamp() * 1000) + len(results),
            'title': clean_chunk.capitalize(),
            'due_date': dt.isoformat() if dt else None,
            'category': category,
            'notify': True,
            'completed': False,
            'reminded': False
        })
    return jsonify(results)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
