from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_cors import CORS
import requests
import subprocess
import os
import tempfile
import shutil
import threading
import time
import uuid
import json
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'ziad-host-secret-key-2024'
CORS(app)

# Firebase REST API config
FIREBASE_API_KEY = 'AIzaSyC_ErlEeBP50IpvEPosZYR3W5jtUNpAP8U'
FIREBASE_AUTH_DOMAIN = 'x-store-19a3b.firebaseapp.com'
FIREBASE_DB_URL = 'https://x-store-19a3b-default-rtdb.firebaseio.com'
FIREBASE_PROJECT_ID = 'x-store-19a3b'

# Admin emails
ADMIN_EMAILS = ['rchglgfsp@gmail.com']

# Store active processes
active_processes = {}
process_logs = {}

# ============================================
# Helper Functions
# ============================================

def add_log(server_id, message):
    if server_id not in process_logs:
        process_logs[server_id] = []
    timestamp = datetime.now().strftime('%H:%M:%S')
    process_logs[server_id].append(f'[{timestamp}] {message}')
    if len(process_logs[server_id]) > 2000:
        process_logs[server_id] = process_logs[server_id][-2000:]

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login_page'))
        user_email = session.get('user', {}).get('email', '')
        if user_email not in ADMIN_EMAILS:
            return "غير مصرح لك بالدخول", 403
        return f(*args, **kwargs)
    return decorated_function

def get_user_data(uid):
    url = f"{FIREBASE_DB_URL}/users/{uid}.json"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json() or {'balance': 0, 'serverCount': 0, 'plan': 'free'}
    except:
        pass
    return {'balance': 0, 'serverCount': 0, 'plan': 'free'}

def update_user_data(uid, data):
    url = f"{FIREBASE_DB_URL}/users/{uid}.json"
    try:
        requests.patch(url, json=data)
    except:
        pass

def get_user_servers(uid):
    url = f"{FIREBASE_DB_URL}/servers.json"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            servers = response.json() or {}
            user_servers = []
            for sid, s in servers.items():
                if s.get('ownerId') == uid:
                    user_servers.append({'id': sid, **s})
            return user_servers
    except:
        pass
    return []

def get_all_servers():
    url = f"{FIREBASE_DB_URL}/servers.json"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            servers = response.json() or {}
            return [{'id': k, **v} for k, v in servers.items()]
    except:
        pass
    return []

def get_all_users():
    url = f"{FIREBASE_DB_URL}/users.json"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            users = response.json() or {}
            return [{'uid': k, **v} for k, v in users.items()]
    except:
        pass
    return []

def get_recharge_requests():
    url = f"{FIREBASE_DB_URL}/rechargeRequests.json"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            requests_data = response.json() or {}
            return [{'id': k, **v} for k, v in requests_data.items()]
    except:
        pass
    return []

def create_server(owner_id, name, language, version, plan):
    server_id = str(uuid.uuid4())[:8]
    server_data = {
        'ownerId': owner_id,
        'name': name,
        'language': language,
        'version': version,
        'status': 'starting',
        'plan': plan,
        'ip': f"10.0.{hash(server_id) % 255}.{hash(server_id + 'ip') % 255}",
        'cpu': 0,
        'ram': 0,
        'createdAt': datetime.now().isoformat(),
        'expiresAt': None
    }
    
    if plan == 'premium':
        from datetime import timedelta
        server_data['expiresAt'] = (datetime.now() + timedelta(days=30)).isoformat()
    
    url = f"{FIREBASE_DB_URL}/servers/{server_id}.json"
    response = requests.put(url, json=server_data)
    
    if response.status_code == 200:
        return server_id
    return None

# ============================================
# Routes - Pages
# ============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login_page():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user = session.get('user', {})
    uid = user.get('localId')
    user_data = get_user_data(uid)
    servers = get_user_servers(uid)
    return render_template('dashboard.html', user=user, user_data=user_data, servers=servers)

@app.route('/server/<server_id>')
@login_required
def server_detail(server_id):
    user = session.get('user', {})
    uid = user.get('localId')
    
    url = f"{FIREBASE_DB_URL}/servers/{server_id}.json"
    response = requests.get(url)
    if response.status_code == 200:
        server = response.json()
        if server and server.get('ownerId') == uid:
            logs = process_logs.get(server_id, [])
            return render_template('server_detail.html', server={'id': server_id, **server}, logs=logs)
    return redirect(url_for('dashboard'))

@app.route('/recharge')
@login_required
def recharge_page():
    user = session.get('user', {})
    return render_template('recharge.html', user=user)

@app.route('/admin')
@admin_required
def admin_panel():
    users = get_all_users()
    servers = get_all_servers()
    requests_data = get_recharge_requests()
    return render_template('admin_panel.html', users=users, servers=servers, requests=requests_data)

# ============================================
# API Routes
# ============================================

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    response = requests.post(url, json={'email': email, 'password': password, 'returnSecureToken': True})
    
    if response.status_code == 200:
        user_data = response.json()
        session['user'] = user_data
        
        # Create user profile if not exists
        uid = user_data.get('localId')
        user_profile = get_user_data(uid)
        if not user_profile:
            is_admin = email in ADMIN_EMAILS
            profile = {
                'email': email,
                'balance': 0,
                'serverCount': 0,
                'plan': 'unlimited' if is_admin else 'free',
                'role': 'admin' if is_admin else 'user',
                'createdAt': datetime.now().isoformat()
            }
            update_user_data(uid, profile)
        
        return jsonify({'status': 'success', 'user': user_data})
    else:
        return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    display_name = data.get('displayName', '')
    
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    response = requests.post(url, json={'email': email, 'password': password, 'returnSecureToken': True})
    
    if response.status_code == 200:
        user_data = response.json()
        session['user'] = user_data
        
        uid = user_data.get('localId')
        is_admin = email in ADMIN_EMAILS
        profile = {
            'email': email,
            'displayName': display_name,
            'balance': 0,
            'serverCount': 0,
            'plan': 'unlimited' if is_admin else 'free',
            'role': 'admin' if is_admin else 'user',
            'createdAt': datetime.now().isoformat()
        }
        update_user_data(uid, profile)
        
        return jsonify({'status': 'success', 'user': user_data})
    else:
        return jsonify({'status': 'error', 'message': 'Registration failed'}), 400

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'status': 'success'})

@app.route('/api/auth/me', methods=['GET'])
@login_required
def auth_me():
    user = session.get('user', {})
    uid = user.get('localId')
    user_data = get_user_data(uid)
    return jsonify({'user': user, 'profile': user_data})

@app.route('/api/servers', methods=['GET'])
@login_required
def api_get_servers():
    user = session.get('user', {})
    uid = user.get('localId')
    servers = get_user_servers(uid)
    return jsonify({'servers': servers})

@app.route('/api/servers', methods=['POST'])
@login_required
def api_create_server():
    user = session.get('user', {})
    uid = user.get('localId')
    data = request.json
    
    server_id = create_server(
        uid,
        data.get('name'),
        data.get('language', 'python'),
        data.get('version', '3.10'),
        data.get('plan', 'free')
    )
    
    if server_id:
        return jsonify({'status': 'success', 'serverId': server_id})
    return jsonify({'status': 'error', 'message': 'Failed to create server'}), 500

@app.route('/api/servers/<server_id>', methods=['DELETE'])
@login_required
def api_delete_server(server_id):
    user = session.get('user', {})
    uid = user.get('localId')
    
    # Check ownership
    url = f"{FIREBASE_DB_URL}/servers/{server_id}.json"
    response = requests.get(url)
    if response.status_code == 200:
        server = response.json()
        if server and server.get('ownerId') == uid:
            # Stop process if running
            if server_id in active_processes:
                try:
                    active_processes[server_id].terminate()
                except:
                    pass
                del active_processes[server_id]
            
            # Delete from Firebase
            requests.delete(url)
            return jsonify({'status': 'success'})
    
    return jsonify({'status': 'error', 'message': 'Server not found'}), 404

@app.route('/api/servers/<server_id>/status', methods=['PUT'])
@login_required
def api_update_server_status(server_id):
    user = session.get('user', {})
    uid = user.get('localId')
    data = request.json
    new_status = data.get('status')
    
    url = f"{FIREBASE_DB_URL}/servers/{server_id}.json"
    response = requests.get(url)
    if response.status_code == 200:
        server = response.json()
        if server and server.get('ownerId') == uid:
            update_url = f"{FIREBASE_DB_URL}/servers/{server_id}/status.json"
            requests.put(update_url, json=new_status)
            return jsonify({'status': 'success'})
    
    return jsonify({'status': 'error', 'message': 'Server not found'}), 404

@app.route('/api/execute', methods=['POST'])
@login_required
def api_execute():
    data = request.json
    language = data.get('language')
    files = data.get('files', [])
    main_file = data.get('main')
    server_id = data.get('serverId')
    
    if not server_id or not files:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Kill existing process
    if server_id in active_processes:
        try:
            active_processes[server_id].terminate()
        except:
            pass
        del active_processes[server_id]
    
    # Initialize logs
    process_logs[server_id] = [f'[SYSTEM] Ziad Host - Initializing {language} environment...']
    add_log(server_id, f'[SYSTEM] Starting server with main file: {main_file}')
    
    def run_code():
        temp_dir = tempfile.mkdtemp(prefix=f'ziad_{server_id}_')
        
        try:
            # Write all files
            for file in files:
                file_path = os.path.join(temp_dir, file['name'])
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(file.get('content', ''))
                add_log(server_id, f'[SYSTEM] Created file: {file["name"]}')
            
            # Determine command
            command = ''
            if language == 'python':
                req_file = next((f for f in files if f['name'] == 'requirements.txt'), None)
                if req_file and req_file.get('content'):
                    add_log(server_id, '[SYSTEM] Installing Python requirements...')
                    subprocess.run(['pip3', 'install', '-r', 'requirements.txt'], cwd=temp_dir, capture_output=True)
                command = f'python3 {main_file}'
            elif language == 'javascript':
                pkg_file = next((f for f in files if f['name'] == 'package.json'), None)
                if pkg_file and pkg_file.get('content'):
                    add_log(server_id, '[SYSTEM] Installing npm dependencies...')
                    subprocess.run(['npm', 'install', '--production'], cwd=temp_dir, capture_output=True)
                command = f'node {main_file}'
            elif language == 'php':
                command = f'php {main_file}'
            else:
                add_log(server_id, f'[ERROR] Language {language} not supported')
                return
            
            add_log(server_id, f'[SYSTEM] Running: {command}')
            
            process = subprocess.Popen(
                command, shell=True, cwd=temp_dir,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1
            )
            
            active_processes[server_id] = process
            
            for line in iter(process.stdout.readline, ''):
                if line:
                    add_log(server_id, line.strip())
            
            for line in iter(process.stderr.readline, ''):
                if line:
                    add_log(server_id, f'[STDERR] {line.strip()}')
            
            process.wait()
            add_log(server_id, f'[SYSTEM] Process exited with code {process.returncode}')
            
            if server_id in active_processes:
                del active_processes[server_id]
        except Exception as e:
            add_log(server_id, f'[ERROR] {str(e)}')
        finally:
            def cleanup():
                time.sleep(30)
                shutil.rmtree(temp_dir, ignore_errors=True)
            threading.Thread(target=cleanup).start()
    
    threading.Thread(target=run_code).start()
    return jsonify({'status': 'started'})

@app.route('/api/stop', methods=['POST'])
@login_required
def api_stop():
    data = request.json
    server_id = data.get('serverId')
    
    if server_id in active_processes:
        try:
            active_processes[server_id].terminate()
            active_processes[server_id].kill()
            del active_processes[server_id]
            add_log(server_id, '[SYSTEM] Server stopped by user')
            return jsonify({'status': 'stopped'})
        except:
            pass
    
    return jsonify({'status': 'not_running'})

@app.route('/api/logs/<server_id>', methods=['GET'])
@login_required
def api_logs(server_id):
    logs = process_logs.get(server_id, [])
    return jsonify({'logs': logs})

@app.route('/api/recharge', methods=['POST'])
@login_required
def api_recharge():
    user = session.get('user', {})
    uid = user.get('localId')
    user_email = user.get('email')
    data = request.json
    
    request_id = str(uuid.uuid4())[:8]
    request_data = {
        'uid': uid,
        'email': user_email,
        'amount': data.get('amount'),
        'telegram': data.get('telegram'),
        'transferNumber': data.get('transferNumber'),
        'status': 'pending',
        'createdAt': datetime.now().isoformat()
    }
    
    url = f"{FIREBASE_DB_URL}/rechargeRequests/{request_id}.json"
    requests.put(url, json=request_data)
    
    return jsonify({'status': 'success'})

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_users():
    users = get_all_users()
    return jsonify({'users': users})

@app.route('/api/admin/users/<uid>/balance', methods=['POST'])
@admin_required
def api_admin_update_balance(uid):
    data = request.json
    amount = data.get('amount')
    operation = data.get('operation', 'add')
    
    user_data = get_user_data(uid)
    current_balance = user_data.get('balance', 0)
    
    if operation == 'add':
        new_balance = current_balance + amount
    else:
        new_balance = max(0, current_balance - amount)
    
    update_user_data(uid, {'balance': new_balance})
    return jsonify({'status': 'success', 'balance': new_balance})

@app.route('/api/admin/users/<uid>/ban', methods=['POST'])
@admin_required
def api_admin_ban_user(uid):
    data = request.json
    is_banned = data.get('isBanned', True)
    update_user_data(uid, {'isBanned': is_banned})
    return jsonify({'status': 'success'})

@app.route('/api/admin/requests/<request_id>/approve', methods=['POST'])
@admin_required
def api_admin_approve_request(request_id):
    url = f"{FIREBASE_DB_URL}/rechargeRequests/{request_id}.json"
    response = requests.get(url)
    if response.status_code == 200:
        req = response.json()
        if req:
            # Update user balance
            uid = req.get('uid')
            amount = req.get('amount', 0)
            user_data = get_user_data(uid)
            current_balance = user_data.get('balance', 0)
            update_user_data(uid, {'balance': current_balance + amount})
            
            # Update request status
            update_url = f"{FIREBASE_DB_URL}/rechargeRequests/{request_id}/status.json"
            requests.put(update_url, json='approved')
            
            return jsonify({'status': 'success'})
    
    return jsonify({'status': 'error'}), 404

@app.route('/api/admin/requests/<request_id>/reject', methods=['POST'])
@admin_required
def api_admin_reject_request(request_id):
    update_url = f"{FIREBASE_DB_URL}/rechargeRequests/{request_id}/status.json"
    requests.put(update_url, json='rejected')
    return jsonify({'status': 'success'})

@app.route('/api/admin/settings', methods=['GET', 'POST'])
@admin_required
def api_admin_settings():
    settings_url = f"{FIREBASE_DB_URL}/settings.json"
    
    if request.method == 'GET':
        response = requests.get(settings_url)
        if response.status_code == 200:
            return jsonify(response.json() or {})
        return jsonify({})
    
    elif request.method == 'POST':
        data = request.json
        requests.put(settings_url, json=data)
        return jsonify({'status': 'success'})

# ============================================
# Run App
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Ziad Host is running on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)