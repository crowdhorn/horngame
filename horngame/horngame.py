# -*- coding: utf-8 -*-
import os
from sqlite3 import dbapi2 as sqlite3
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
from werkzeug.security import generate_password_hash, check_password_hash
import json
import datetime, time
import tool.solution
import tool.common
import random
import threading
import logging

# create our little application :)
app = Flask(__name__)

# Load default config and override config from an environment variable
app.config.update(dict(
    DATABASE=os.path.join(app.root_path, 'horngame.db'),
    DEBUG=True,
    SECRET_KEY='this is the horngame secret key that is super secret and super key',
    LOGGING_LEVEL=logging.DEBUG,
    LOGGING_FILE='horngame.log',
    LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
app.config.from_envvar('HORNGAME_SETTINGS', silent=True)

# Logging
formatter = logging.Formatter(app.config['LOGGING_FORMAT'])
handler = logging.FileHandler(app.config['LOGGING_FILE'])
handler.setLevel(app.config['LOGGING_LEVEL'])
handler.setFormatter(formatter)
app.logger.addHandler(handler)

###############################################################################
# Website
###############################################################################

@app.route('/')
def home():
    users = get_users(limit=100)
    ntasks = get_nb_tasks()
    nproblems = get_nb_problems()
    db = get_db()
    cur = db.execute('select count(id) as total from problems_solved');
    nproblemssolved = cur.fetchone()['total']
    db = get_db()
    cur = db.execute('select count(id) as total from attempts where success=1');
    nsolutions = cur.fetchone()['total']
    if not nproblemssolved:
        nproblemssolved = 0
    if not nsolutions:
        nsolutions = 0
    return render_template('home.html', users=users, ntasks=ntasks, nproblems=nproblems, nproblemssolved=nproblemssolved, nsolutions=nsolutions)

def clean_clauses(task):
    t = task.copy()
    for i in range(len(t['clauses'])):
        clause_split = t['clauses'][i].split('; ')
        index = sum(1 if c.startswith('\\forall') else 0 for c in clause_split)
        t['clauses'][i] = '; '.join(clause_split[index:])
    return t

@app.route('/play')
def play():
    if 'logged_in_game' not in session:
        return redirect(url_for('login'))

    # Select all the solved tasks
    db = get_db()
    cur = db.execute('select * from attempts where user_id=? and success=1', [session['id']])
    solved = cur.fetchall()
    
    # Get all the tasks
    tasks = get_tasks(sort_by="difficulty")

    # Render the template
    return render_template('play.html', tasks=tasks, solved=solved)

@app.route('/play/<string:tid>', methods=['POST', 'GET'])
def play_task(tid):
    if 'logged_in_game' not in session:
        return redirect(url_for('login'))

    # Helper functions
    def fetch_history(db, task_id):
        cur = db.execute(
        'select u.username as username, min(a.duration) as duration, a.submitDate as submitDate from users as u, attempts as a where a.user_id=u.id and a.success=1 and a.task_id = ? group by u.id order by a.duration asc', [task_id])
        return cur.fetchall()

    def fetch_user_previous_solutions(db, task_id):
        cur = db.execute(
        'select * from attempts where task_id=? and user_id=? and success=1 order by submitDate asc', [task_id, session['id']])
        try:
            return json.loads(cur.fetchone()['json'])['preds']
        except:
            return []

    db = get_db()
    if request.method == 'POST':
        # Load the task
        try:
            task = get_task_from_tid(tid, clean=False)
        except:
            return render_template('error.html', error_msg="This task does not exist.")
        # Modify the assignments in the task
        texterror = ""
        for i in range(len(task['preds'])):
            if request.form[task['preds'][i]['name']] == "false":
                texterror = 'Oh yes, we forgot to say, but please do not use the predicate <strong>false</strong> :^)'
            task['preds'][i]['assignment'] = request.form[task['preds'][i]['name']]

        if texterror:
            return render_template('play_task.html', task=clean_clauses(task), history=fetch_history(db, task['task_id']), texterror=texterror, previous=fetch_user_previous_solutions(db, task['task_id']))
        
        # Check the new solution
        try:
            valid_clauses = tool.solution.check_solution(task, os.path.join(app.static_folder, tool.common.PROBLEM_DIR_SUFFIX))
            app.logger.info('check_solution: %s', str(valid_clauses))
        except SyntaxError as texterror:
            app.logger.error(texterror)
            return render_template('play_task.html', task=clean_clauses(task), history=fetch_history(db, task['task_id']), texterror=texterror, previous=fetch_user_previous_solutions(db, task['task_id']))
        except tool.solution.InconsistentPredicateException as tauterror:
            errortext = ("Dude, don't use inconsistent formulas for {}!".format(tauterror))
            app.logger.error(errortext)
            return render_template('play_task.html', task=clean_clauses(task), history=fetch_history(db, task['task_id']), texterror=errortext, previous=fetch_user_previous_solutions(db, task['task_id']))
        # Success bool
        success = (valid_clauses == [1]*len(valid_clauses))

        # Update nsolved and nerrors
        session['nerrors'] += 0 if success else 1
        if success:
            cur = db.execute('select * from attempts where success=1 and task_id=? and user_id=?', [task['task_id'], session['id']])
            attempts = cur.fetchall()
            if len(attempts) == 0:
                session['nsolved'] += 1
        save_session()

        # Value for database
        value = 0
        if success:
            value = 1
        elif 0 not in valid_clauses:
            value = 2

        # Select if interesting to verify the problem with this attempt
        verified = 0 if value != 0 else 1 
        
        # Add the attempt to the database
        cur = db.execute('insert into attempts (user_id, task_id, json, result, submitDate, duration, success, verified) values (?, ?, ?, ?, ?, ?, ?, ?)', [ session['id'], task['task_id'], json.dumps(task), str(valid_clauses), datetime.datetime.utcfromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), int(time.time())-session['starttime_%s'%tid], value, verified])
        db.commit()

        # Background check
        if value != 0:
            th = threading.Thread(target=verify_if_we_can_solve_problem, args=(cur.lastrowid,))
            th.start()
            # verify_if_we_can_solve_problem(cur.lastrowid)

        # INSUCCESS CASE
        if success == False: 
            error = valid_clauses
            return render_template('play_task.html', task=clean_clauses(task), history=fetch_history(db, task['task_id']), error=error, previous=fetch_user_previous_solutions(db, task['task_id']))
        else:
            return render_template('play_task.html', task=clean_clauses(task), history=fetch_history(db, task['task_id']), previous=fetch_user_previous_solutions(db, task['task_id']))
    elif request.method == 'GET':
        # Load the task
        try:
            task = get_task_from_tid(tid)
        except:
            app.logger.error("Task %s does not exist.", tid)
            return render_template('error.html', error_msg="This task does not exist.")
        if 'starttime_%s'%tid not in session:
            session['starttime_%s'%tid] = int(time.time())
        return render_template('play_task.html', task=task, history=fetch_history(db, task['task_id']), previous=fetch_user_previous_solutions(db, task['task_id']))
    else:
        app.logger.error("You should not be here. Request: %s", str(request))
        return render_template('error.html', error_msg="You should not be here.")

@app.route('/solutions')
def solutions():
    if 'logged_in_game' not in session:
        return redirect(url_for('home'))
    if session['admin'] != True:
        return redirect(url_for('home'))

    # You are admin

    db = get_db()
    cur = db.execute('select * from attempts where success=1')
    solutions = cur.fetchall()

    cur = db.execute('select * from attempts where success=0')
    fails = cur.fetchall()

    cur = db.execute('select * from attempts where success=2')
    timeouts = cur.fetchall()

    return render_template('solutions.html', solutions=solutions, fails=fails, timeouts=timeouts)

@app.route('/solved')
def solved():
    if 'logged_in_game' not in session:
        return redirect(url_for('home'))
    if session['admin'] != True:
        return redirect(url_for('home'))

    # You are admin
    db = get_db()
    cur = db.execute('select p.problem_id as pid, a.json as task from problems_solved as p, attempts as a where p.attempt_id = a.id')
    solved = cur.fetchall()

    return render_template('solved.html', solved=solved)

###############################################################################
## Login / logout
###############################################################################

def save_session():
    if 'logged_in_game' in session:
        db = get_db()
        db.execute('update users set nsolved = ?, nerrors = ? where id = ?', [session['nsolved'], session['nerrors'], session['id']])
        db.commit()

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    username = ""
    if request.method == 'POST':
        db = get_db()
        cur = db.execute('select id, password, admin, nsolved, nerrors from users where username = ? limit 1', [request.form['username']])
        user = cur.fetchone()

        if 'signup' in request.form:
            if user:
                error = 'This username is already taken'
                username = request.form['username']
            elif request.form['username'].replace(' ', '') == '':
                error = 'The username is empty'
            elif request.form['password'].replace(' ', '') == '':
                error = 'The password is empty'
                username = request.form['username']
            else:
                db.execute('insert into users (username, password) values (?, ?)', [ request.form['username'], generate_password_hash(request.form['password']) ])
                db.commit()
                cur = db.execute('select id, password, admin, nsolved, nerrors from users where username = ? limit 1', [request.form['username']])
                user = cur.fetchone()

        if error:
            return render_template('login.html', error=error, username=username)
        if user:
            if check_password_hash(user['password'], request.form['password']):
                session['logged_in_game'] = True
                session['admin'] = (user['admin'] == 1)
                session['username'] = request.form['username']
                session['id'] = user['id']
                session['nsolved'] = user['nsolved']
                session['nerrors'] = user['nerrors']
                return redirect(url_for('play'))
            else:
                error = 'Invalid password'
                username = request.form['username']
        else:
            error = 'Invalid username'
    return render_template('login.html', error=error, username=username)


@app.route('/logout')
def logout():
    session.pop('admin', None)
    session.pop('logged_in_game', None)
    session.pop('username', None)
    session.pop('id', None)
    session.pop('nsolved', None)
    session.pop('nerrors', None)
    for key in session.keys():
        if key.startswith('starttime'):
            session.pop(key, None)
    return redirect(url_for('home'))


###############################################################################
# User-related functions
###############################################################################

def get_nb_users():
    """ Return the number of users """
    db = get_db()
    cur = db.execute('select count(id) as nusers from users')
    return cur.fetchone()['nusers']

def get_users(limit=None):
    db = get_db()
    query = 'select id, username, nsolved, nerrors from users order by nsolved desc'
    if limit and limit > 0:
        query += ' limit %d' % limit
    cur = db.execute(query)
    return cur.fetchall()


###############################################################################
# Database-related functions
###############################################################################
def connect_db():
    """Connects to the specific database."""
    rv = sqlite3.connect(app.config['DATABASE'])
    rv.row_factory = sqlite3.Row
    return rv


def init_db():
    """Initializes the database."""
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()


def populate_db():
    """Populate the database tables."""
    db = get_db()
    with app.open_resource('populate.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = connect_db()
    return g.sqlite_db


@app.teardown_appcontext  # automatically close the database at the closing
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()


###############################################################################
# Command line
###############################################################################

def verify_if_we_can_solve_problem(aid):
    with app.app_context():
        db = get_db()

        cur = db.execute('select * from attempts where id=?', [aid])
        attempt = cur.fetchone()

        # Use the task
        db.execute('update attempts set verified = 1 where id = ?', [attempt['id']])
        db.commit()

        task = json.loads(attempt['json'])
    
        cur = db.execute('select problem_id from problems_solved where problem_id = ?', [task['problem_id']])
        problem = cur.fetchall()
        app.logger.info('check the problem: %s', str(problem))
        if problem:
            db.execute('update attempts set verified = 1 where id = ?', [attempt['id']])
            db.commit()
            return
        problem_id, solved, generated_tasks = tool.solution.check_solution_against_smt_file(task, os.path.join(app.static_folder, tool.common.PROBLEM_DIR_SUFFIX), app.root_path)
        app.logger.info('For problem: %s. Solved? %s. New Tasks %s', str(problem_id), str(solved), str(generated_tasks))
        if solved:
            db.execute('insert into problems_solved (attempt_id, problem_id, verificationDate) values (?,?,?)', [attempt['id'], task['problem_id'], datetime.datetime.utcfromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')])
            db.commit()
        db.execute('update attempts set verified = 1 where id = ?', [attempt['id']])
        db.commit()
    

###############################################################################
# Command line
###############################################################################


@app.cli.command('initdb')
def initdb_command():
    """CLI to initialize the database."""
    init_db()
    app.logger.info('Initialized the database.')
    print('Initialized the database.')

@app.cli.command('populatedb')
def populatedb_command():
    """CLI to populate the database tables."""
    populate_db()
    app.logger.info('Populated the database.')
    print('Populated the database.')

@app.cli.command('solutions')
def save_solutions():
    db = get_db()
    cur = db.execute('select * from attempts')
    for attempt in cur.fetchall():
        solution_path = os.path.join(app.root_path, 'solutions')
        if not os.path.exists(solution_path):
          os.makedirs(solution_path)
        with open(os.path.join(solution_path, 'solution_%d.json'%attempt['id']), 'w') as f:
            sol = json.loads(attempt['json'])
            sol['valid_clauses'] = attempt['result']
            json.dump(sol, f)

###############################################################################
# Json-related functions
###############################################################################

def get_nb_tasks():
    n = 0
    names_tasks = os.listdir(os.path.join(app.static_folder, tool.common.PROBLEM_DIR_SUFFIX))
    for file in names_tasks:
        if file.startswith('task'):
            n += 1
    return n

def get_nb_problems():
    n = 0
    names_tasks = os.listdir(os.path.join(app.static_folder, tool.common.PROBLEM_DIR_SUFFIX))
    for file in names_tasks:
        if file.startswith('problem'):
            n += 1
    return n

def get_task_from_tid(tid, clean=True):
    return get_task_from_filename('task_%s.json'%tid, clean)

def get_task_from_filename(filename, clean=True):
    with app.open_resource(os.path.join(app.static_folder, tool.common.PROBLEM_DIR_SUFFIX, filename), mode='r') as f:
        task = json.load(f)
        return clean_clauses(task) if clean else task
    return json.loads("{}")

def get_tasks(sort_by="default"):
    all_tasks = []
    names_tasks = os.listdir(os.path.join(app.static_folder, tool.common.PROBLEM_DIR_SUFFIX))
    for file in names_tasks:
        if file[:4] == 'task' and file[-4:]=='json':
            all_tasks += [get_task_from_filename(file)]
    if sort_by=="difficulty":
        return sorted(all_tasks, key=lambda t: len(t['clauses']))
    else:
        return sorted(all_tasks, key=lambda t: t['task_id'])
