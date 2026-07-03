from flask import Flask, render_template, request, redirect, url_for, flash
import json
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'job_hunting_app_secret_key_for_pbl'

DATA_FILE = 'data.json'

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"companies": [], "tasks": [], "schedules": []}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"companies": [], "tasks": [], "schedules": []}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ─── ルーティング ───

@app.route('/')
def index():
    """最終版ダッシュボード：タスク、スケジュール、およびステータス別企業一覧"""
    data = load_data()
    
    company_map = {c['id']: c['name'] for c in data['companies']}
    
    # --- タスクデータの処理 (ステップ2) ---
    today = datetime.now().date()
    display_tasks = []
    for t in data['tasks']:
        try:
            deadline_date = datetime.strptime(t['deadline'], '%Y-%m-%d').date()
            days_left = (deadline_date - today).days
        except ValueError:
            days_left = None

        display_tasks.append({
            "id": t['id'],
            "company_name": company_map.get(t['company_id'], "不明な企業"),
            "task_name": t['task_name'],
            "deadline": t['deadline'],
            "is_completed": t['is_completed'],
            "days_left": days_left
        })
    display_tasks.sort(key=lambda x: x['days_left'] if x['days_left'] is not None else 9999)

    # --- スケジュールデータの処理 (ステップ3) ---
    display_schedules = []
    for s in data.get('schedules', []):
        try:
            dt_obj = datetime.strptime(s['event_datetime'], '%Y-%m-%dT%H:%M')
            formatted_datetime = dt_obj.strftime('%Y年%m月%d日 %H:%M')
        except ValueError:
            formatted_datetime = s['event_datetime']
            dt_obj = datetime.max

        display_schedules.append({
            "id": s['id'],
            "company_name": company_map.get(s['company_id'], "不明な企業"),
            "event_name": s['event_name'],
            "event_datetime": formatted_datetime,
            "location": s['location'],
            "dt_obj": dt_obj
        })
    display_schedules.sort(key=lambda x: x['dt_obj'])

    # --- 【新規】ステータス別企業一覧の分類 (ステップ4) ---
    # 要件定義の「出力項目：ステータス別企業一覧」を達成するため辞書でグループ分け
    # 状態遷移図にある5つの状態を初期化
    status_categories = {
        '未応募': [],
        '書類審査中': [],
        '面接待ち': [],
        '内定': [],
        '選考終了': []
    }
    
    for c in data['companies']:
        status = c.get('status', '未応募')
        if status in status_categories:
            status_categories[status].append(c)
        else:
            status_categories['未応募'].append(c) # 万が一のセーフティ

    return render_template('index.html', 
                           companies=data['companies'], 
                           tasks=display_tasks, 
                           schedules=display_schedules,
                           status_categories=status_categories)


@app.route('/company/add', methods=['POST'])
def add_company():
    """企業登録"""
    data = load_data()
    name = request.form.get('name', '').strip()
    status = request.form.get('status', '未応募')
    memo = request.form.get('memo', '').strip()
    
    if not name:
        flash('【エラー】企業名は必須入力です。', 'error')
        return redirect(url_for('index'))
    
    existing_ids = [c['id'] for c in data['companies']]
    next_id = max(existing_ids) + 1 if existing_ids else 1

    new_company = {"id": next_id, "name": name, "status": status, "memo": memo}
    data['companies'].append(new_company)
    save_data(data)
    
    flash(f'企業「{name}」を登録しました。', 'success')
    return redirect(url_for('index'))


@app.route('/company/update/<int:company_id>', methods=['POST'])
def update_company(company_id):
    """【新規追加】状態遷移図に基づくステータス・メモの更新処理（検証付き）"""
    data = load_data()
    
    new_status = request.form.get('status')
    new_memo = request.form.get('memo', '').strip()
    
    # 状態遷移図の有効なステータス定義
    valid_statuses = ['未応募', '書類審査中', '面接待ち', '内定', '選考終了']
    if new_status not in valid_statuses:
        flash('【エラー】不正なステータスへの変更はできません。', 'error')
        return redirect(url_for('index'))

    # 対象企業の検索
    target_company = None
    for c in data['companies']:
        if c['id'] == company_id:
            target_company = c
            break
            
    if not target_company:
        flash('【エラー】更新対象の企業が見つかりませんでした。', 'error')
        return redirect(url_for('index'))
    
    # 【方針4＆設計準拠】状態遷移図ルールの検証
    current_status = target_company.get('status', '未応募')
    
    # 状態遷移図上、「内定」または「選考終了」は終端ステータス（[*]へ向かう）のため、そこからの変更を制限する
    if current_status in ['内定', '選考終了'] and new_status != current_status:
        flash(f'【エラー】すでに「{current_status}」となった企業のステータスを「{new_status}」に変更することはできません（状態遷移図ルール）。', 'error')
        return redirect(url_for('index'))

    # データの更新
    target_company['status'] = new_status
    target_company['memo'] = new_memo
    save_data(data)
    
    flash(f'「{target_company["name"]}」の情報を更新しました。', 'success')
    return redirect(url_for('index'))


@app.route('/task/add', methods=['POST'])
def add_task():
    """タスク登録"""
    data = load_data()
    try:
        company_id = int(request.form.get('company_id', 0))
    except ValueError:
        company_id = 0
    task_name = request.form.get('task_name', '').strip()
    deadline = request.form.get('deadline', '').strip()

    if not task_name or not deadline:
        flash('【エラー】タスク名と締め切り日は必須入力です。', 'error')
        return redirect(url_for('index'))

    valid_company_ids = [c['id'] for c in data['companies']]
    if company_id not in valid_company_ids:
        flash('【エラー】選択された企業が存在しません。', 'error')
        return redirect(url_for('index'))

    existing_ids = [t['id'] for t in data['tasks']]
    next_id = max(existing_ids) + 1 if existing_ids else 1

    new_task = {
        "id": next_id,
        "company_id": company_id,
        "task_name": task_name,
        "deadline": deadline,
        "is_completed": False
    }
    data['tasks'].append(new_task)
    save_data(data)
    
    flash(f'タスク「{task_name}」を登録しました。', 'success')
    return redirect(url_for('index'))


@app.route('/schedule/add', methods=['POST'])
def add_schedule():
    """スケジュール登録"""
    data = load_data()
    try:
        company_id = int(request.form.get('company_id', 0))
    except ValueError:
        company_id = 0
    event_name = request.form.get('event_name', '').strip()
    event_datetime = request.form.get('event_datetime', '').strip()
    location = request.form.get('location', '').strip()

    if not event_name or not event_datetime or not location:
        flash('【エラー】すべての項目を入力してください。', 'error')
        return redirect(url_for('index'))

    valid_company_ids = [c['id'] for c in data['companies']]
    if company_id not in valid_company_ids:
        flash('【エラー】選択された企業が存在しません。', 'error')
        return redirect(url_for('index'))

    if 'schedules' not in data:
        data['schedules'] = []
    existing_ids = [s['id'] for s in data['schedules']]
    next_id = max(existing_ids) + 1 if existing_ids else 1

    new_schedule = {
        "id": next_id,
        "company_id": company_id,
        "event_name": event_name,
        "event_datetime": event_datetime,
        "location": location
    }
    data['schedules'].append(new_schedule)
    save_data(data)
    
    flash(f'予定「{event_name}」を登録しました。', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)