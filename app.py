import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, timedelta
from functools import wraps
import uuid
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

# --- App Configuration & Paths ---
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_very_secret_key_for_development_v10')
NOTIFICATIONS_FILE = 'notifications.json'
USERS_FILE = 'users.json'
CONFIG_FILE = 'site_config.json'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

# --- Helpers ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'xlsx'}

def read_json(file_path):
    is_list_based = 'users' in file_path or 'notifications' in file_path
    default_return = [] if is_list_based else {}
    if not os.path.exists(file_path): return default_return
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return json.loads(content) if content else default_return
    except (json.JSONDecodeError, IOError): return default_return

def write_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

# --- vvv NEW: UNUSED FILE CLEANUP FUNCTION vvv ---
def cleanup_unused_files():
    """Scans for and deletes files in the uploads folder that are no longer referenced."""
    all_notifications = read_json(NOTIFICATIONS_FILE)
    site_config = read_json(CONFIG_FILE)
    used_filenames = set()

    # Get filenames from notifications
    for notif in all_notifications:
        url = notif.get('attachment_url', '')
        if url and '/static/uploads/' in url:
            used_filenames.add(url.split('/')[-1])

    # Get filenames from quick links
    for link in site_config.get('quick_links', []):
        url = link.get('url', '')
        if url and '/static/uploads/' in url:
            used_filenames.add(url.split('/')[-1])
    
    # Compare with files on disk and delete orphans
    if not os.path.exists(UPLOAD_FOLDER): return
    for filename in os.listdir(UPLOAD_FOLDER):
        if filename not in used_filenames:
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, filename))
                print(f"Cleaned up unused file: {filename}") # For server log
            except OSError as e:
                print(f"Error deleting file {filename}: {e}")
# --- ^^^ END OF NEW FUNCTION ^^^ ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session: return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- USER-FACING ROUTES (Unchanged) ---
@app.route('/')
def index():
    site_config = read_json(CONFIG_FILE)
    quick_links = site_config.get('quick_links', [])
    calendar_url = '#'
    for link in quick_links:
        if 'calendar' in link.get('title', '').lower():
            calendar_url = link.get('url', '#')
            break
    return render_template('index.html', quick_links=quick_links, calendar_url=calendar_url)

@app.route('/api/notifications')
def api_notifications():
    all_notifs = read_json(NOTIFICATIONS_FILE)
    now = datetime.utcnow()
    active_notifs, archived_notifs = [], []
    for n in all_notifs:
        if n.get('type') == 'archive':
            archived_notifs.append(n)
            continue
        start_date = datetime.fromisoformat(n.get('start_datetime')) if n.get('start_datetime') else now
        if start_date > now: continue
        is_expired, dynamic_type = False, n.get('type', 'info')
        if n.get('end_datetime') and n['end_datetime']:
            try:
                end_date = datetime.fromisoformat(n['end_datetime'])
                if end_date < now: is_expired = True
                else:
                    time_left = end_date - now
                    if time_left <= timedelta(days=3): dynamic_type = 'urgent'
                    elif time_left <= timedelta(days=7) and dynamic_type != 'urgent': dynamic_type = 'upcoming'
            except (ValueError, TypeError): pass
        if not is_expired:
            n['type'] = dynamic_type
            active_notifs.append(n)
    active_notifs.sort(key=lambda x: x.get('start_datetime', '1970-01-01T00:00:00'), reverse=True)
    archived_notifs.sort(key=lambda x: x.get('start_datetime', '1970-01-01T00:00:00'), reverse=True)
    dept_filter, year_filter = request.args.get('department'), request.args.get('year')
    response_data = {
        'guidelines': [n for n in active_notifs if n.get('type') == 'guideline'],
        'common': [n for n in active_notifs if ('all' in n.get('department', [])) and ('all' in n.get('year', [])) and n.get('type') in ['common', 'info', 'urgent', 'upcoming']],
        'archive': archived_notifs, 'departmental': []
    }
    if dept_filter and year_filter:
        response_data['departmental'] = [ n for n in active_notifs if ('all' in n.get('department', []) or dept_filter in n.get('department', [])) and ('all' in n.get('year', []) or year_filter in n.get('year', [])) and n.get('type') == 'departmental' ]
    return jsonify(response_data)

# --- ADMIN PANEL ROUTES ---
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        users, username, password = read_json(USERS_FILE), request.form['username'], request.form['password']
        user = next((u for u in users if isinstance(u, dict) and u.get('username') == username), None)
        if user and user.get('password') == password:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else: flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin_dashboard():
    notifications = read_json(NOTIFICATIONS_FILE)
    now = datetime.utcnow()
    updated = False
    for notif in notifications:
        if notif.get('type') != 'archive' and notif.get('end_datetime'):
            try:
                if datetime.fromisoformat(notif['end_datetime']) < now:
                    notif['type'] = 'archive'; updated = True
            except (ValueError, TypeError): continue
    if updated: write_json(NOTIFICATIONS_FILE, notifications)
    site_config = read_json(CONFIG_FILE)
    active_notifications = [n for n in notifications if n.get('type') != 'archive']
    archived_notifications = [n for n in notifications if n.get('type') == 'archive']
    return render_template('admin.html', active_notifications=active_notifications, archived_notifications=archived_notifications, quick_links=site_config.get('quick_links', []))

@app.route('/admin/add', methods=['POST'])
@login_required
def add_notification():
    notifications = read_json(NOTIFICATIONS_FILE)
    attachment_path = ''
    if 'attachment_file' in request.files:
        file = request.files['attachment_file']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            attachment_path = url_for('static', filename=f'uploads/{filename}', _external=True)
    new_notif = {
        'id': str(uuid.uuid4()), 'title': request.form['title'], 'body': request.form['body'],
        'type': request.form['type'], 'department': request.form.getlist('department'), 'year': request.form.getlist('year'),
        'attachment_url': attachment_path if attachment_path else request.form.get('attachment_url', ''),
        'is_popup': 'is_popup' in request.form,
        'start_datetime': request.form.get('start_datetime') or datetime.utcnow().isoformat(),
        'end_datetime': request.form.get('end_datetime') if request.form.get('expiry_type') == 'timed' and request.form.get('end_datetime') else None
    }
    notifications.append(new_notif)
    write_json(NOTIFICATIONS_FILE, notifications)
    flash('Notification added successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit/<notification_id>', methods=['POST'])
@login_required
def edit_notification(notification_id):
    notifications = read_json(NOTIFICATIONS_FILE)
    for notif in notifications:
        if notif['id'] == notification_id:
            attachment_path = notif.get('attachment_url', '')
            if request.form.get('attach_type') == 'file' and 'attachment_file' in request.files:
                file = request.files['attachment_file']
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    attachment_path = url_for('static', filename=f'uploads/{filename}', _external=True)
            elif request.form.get('attach_type') == 'url':
                attachment_path = request.form.get('attachment_url', '')
            notif.update({
                'title': request.form['title'], 'body': request.form['body'], 'type': request.form['type'],
                'department': request.form.getlist('department'), 'year': request.form.getlist('year'),
                'is_popup': 'is_popup' in request.form, 'start_datetime': request.form.get('start_datetime'),
                'end_datetime': request.form.get('end_datetime') if request.form.get('expiry_type') == 'timed' and request.form.get('end_datetime') else None,
                'attachment_url': attachment_path
            })
            break
    write_json(NOTIFICATIONS_FILE, notifications)
    cleanup_unused_files() # <-- Call cleanup after edit
    flash('Notification updated successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<notification_id>', methods=['POST'])
@login_required
def delete_notification(notification_id):
    notifications = [n for n in read_json(NOTIFICATIONS_FILE) if n['id'] != notification_id]
    write_json(NOTIFICATIONS_FILE, notifications)
    cleanup_unused_files() # <-- Call cleanup after delete
    flash('Notification deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/links/update', methods=['POST'])
@login_required
def update_config_links():
    site_config = read_json(CONFIG_FILE)
    for i, link in enumerate(site_config.get('quick_links', [])):
        link['title'] = request.form.get(f"title_{i}", link['title'])
        file_key = f'file_{i}'
        if file_key in request.files:
            file = request.files[file_key]
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                link['url'] = url_for('static', filename=f'uploads/{filename}', _external=True)
                continue
        link['url'] = request.form.get(f"url_{i}") or link['url']
    write_json(CONFIG_FILE, site_config)
    cleanup_unused_files() # <-- Call cleanup after link update
    flash('Quick access links updated successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)