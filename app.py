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
FIREBASE_DB_URL = 'https://x-store-19a3b-default-rtdb.firebaseio.com'

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
            data = response.json()
            if data:
                return data
    except Exception as e:
        print(f"Error getting user data: {e}")
    return {'balance': 0, 'serverCount': 0, 'plan': 'free'}

def update_user_data(uid, data):
    url = f"{FIREBASE_DB_URL}/users/{uid}.json"
    try:
        requests.patch(url, json=data)
    except Exception as e:
        print(f"Error updating user data: {e}")

def get_user_servers(uid):
    url = f"{FIREBASE_DB_URL}/servers.json"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            servers = response.json() or {}
            user_servers = []
            for sid, s in servers.items():
                if s and s.get('ownerId') == uid:
                    user_servers.append({'id': sid, **s})
            return user_servers
    except Exception as e:
        print(f"Error getting user servers: {e}")
    return []

def get_all_servers():
    url = f"{FIREBASE_DB_URL}/servers.json"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            servers = response.json() or {}
            return [{'id': k, **v} for k, v in servers.items() if v]
    except Exception as e:
        print(f"Error getting all servers: {e}")
    return []

def get_all_users():
    url = f"{FIREBASE_DB_URL}/users.json"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            users = response.json() or {}
            return [{'uid': k, **v} for k, v in users.items() if v]
    except Exception as e:
        print(f"Error getting all users: {e}")
    return []

def get_recharge_requests():
    url = f"{FIREBASE_DB_URL}/rechargeRequests.json"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            requests_data = response.json() or {}
            return [{'id': k, **v} for k, v in requests_data.items() if v]
    except Exception as e:
        print(f"Error getting recharge requests: {e}")
    return []

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
    try:
        response = requests.get(url)
        if response.status_code == 200:
            server = response.json()
            if server and server.get('ownerId') == uid:
                logs = process_logs.get(server_id, [])
                return render_template('server_detail.html', server={'id': server_id, **server}, logs=logs)
    except Exception as e:
        print(f"Error getting server detail: {e}")
    
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
    try:
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
            if not user_profile or not user_profile.get('email'):
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
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    try:
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
    except Exception as e:
        print(f"Register error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
    try:
        user = session.get('user', {})
        uid = user.get('localId')
        data = request.json
        
        server_id = str(uuid.uuid4())[:8]
        server_data = {
            'ownerId': uid,
            'name': data.get('name'),
            'language': data.get('language', 'python'),
            'version': data.get('version', '3.10'),
            'status': 'stopped',
            'plan': data.get('plan', 'free'),
            'ip': f"10.0.{hash(server_id) % 255}.{hash(server_id + 'ip') % 255}",
            'cpu': 0,
            'ram': 0,
            'createdAt': datetime.now().isoformat()
        }
        
        url = f"{FIREBASE_DB_URL}/servers/{server_id}.json"
        response = requests.put(url, json=server_data)
        
        if response.status_code == 200:
            # Update user server count
            user_data = get_user_data(uid)
            current_count = user_data.get('serverCount', 0)
            update_user_data(uid, {'serverCount': current_count + 1})
            return jsonify({'status': 'success', 'serverId': server_id})
        
        return jsonify({'status': 'error', 'message': 'Failed to create server'}), 500
    except Exception as e:
        print(f"Create server error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/servers/<server_id>', methods=['DELETE'])
@login_required
def api_delete_server(server_id):
    try:
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
                
                # Update user server count
                user_data = get_user_data(uid)
                current_count = user_data.get('serverCount', 0)
                update_user_data(uid, {'serverCount': max(0, current_count - 1)})
                
                return jsonify({'status': 'success'})
        
        return jsonify({'status': 'error', 'message': 'Server not found'}), 404
    except Exception as e:
        print(f"Delete server error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/servers/<server_id>/status', methods=['PUT'])
@login_required
def api_update_server_status(server_id):
    try:
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
    except Exception as e:
        print(f"Update status error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/execute', methods=['POST'])
@login_required
def api_execute():
    try:
        data = request.json
        language = data.get('language')
        files = data.get('files', [])
        main_file = data.get('main')
        server_id = data.get('serverId')
        
        if not server_id:
            return jsonify({'error': 'Missing serverId'}), 400
        
        # Initialize logs
        process_logs[server_id] = [f'[SYSTEM] Ziad Host - Initializing {language} environment...']
        add_log(server_id, f'[SYSTEM] Starting server with main file: {main_file}')
        
        return jsonify({'status': 'started'})
    except Exception as e:
        print(f"Execute error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stop', methods=['POST'])
@login_required
def api_stop():
    try:
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
    except Exception as e:
        print(f"Stop error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/<server_id>', methods=['GET'])
@login_required
def api_logs(server_id):
    logs = process_logs.get(server_id, [])
    return jsonify({'logs': logs})

@app.route('/api/recharge', methods=['POST'])
@login_required
def api_recharge():
    try:
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
    except Exception as e:
        print(f"Recharge error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_users():
    users = get_all_users()
    return jsonify({'users': users})

@app.route('/api/admin/users/<uid>/balance', methods=['POST'])
@admin_required
def api_admin_update_balance(uid):
    try:
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
    except Exception as e:
        print(f"Update balance error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/users/<uid>/ban', methods=['POST'])
@admin_required
def api_admin_ban_user(uid):
    try:
        data = request.json
        is_banned = data.get('isBanned', True)
        update_user_data(uid, {'isBanned': is_banned})
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"Ban user error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/requests/<request_id>/approve', methods=['POST'])
@admin_required
def api_admin_approve_request(request_id):
    try:
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
    except Exception as e:
        print(f"Approve request error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/requests/<request_id>/reject', methods=['POST'])
@admin_required
def api_admin_reject_request(request_id):
    try:
        update_url = f"{FIREBASE_DB_URL}/rechargeRequests/{request_id}/status.json"
        requests.put(update_url, json='rejected')
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"Reject request error: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================
# Run App
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Ziad Host is running on http://localhost:{port}")
    print(f"📍 Firebase DB: {FIREBASE_DB_URL}")
    app.run(host='0.0.0.0', port=port, debug=True)