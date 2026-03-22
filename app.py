from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from pymysql import IntegrityError
import os
import pymysql

pymysql.install_as_MySQLdb()

app = Flask(__name__)
app.secret_key = 'police_erp_secret'

# ---------- DB CONFIG ----------
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'shuttle.proxy.rlwy.net')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', 'XRdJNIUEJYSCaqRcokOOQZCKEVggylMZ')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB', 'railway')
app.config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT', 26508))

def get_db():
    return pymysql.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB'],
        port=app.config['MYSQL_PORT'],
        cursorclass=pymysql.cursors.DictCursor
    )

# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db()
        cur = conn.cursor()

        username = request.form['username']
        password = request.form['password']

        cur.execute(
            "SELECT role FROM users WHERE username=%s AND password=%s",
            (username, password)
        )
        user = cur.fetchone()

        if user:
            session['role'] = user['role']
            session['username'] = username

            if user['role'] == 'police':
                session['officer_id'] = user['user_id']

            cur.execute("INSERT INTO login_logs(username) VALUES (%s)", (username,))
            conn.commit()

            cur.close(); conn.close()
            return redirect('/police_dashboard')

        cur.close(); conn.close()

    return render_template('login.html')

# ---------- HOME ----------
@app.route('/')
def home():
    return render_template("home.html")

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------- DASHBOARD ----------
@app.route('/police_dashboard')
def police_dashboard():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT city, latitude, longitude, COUNT(*) AS total_cases
        FROM fir
        GROUP BY city, latitude, longitude
    """)
    crime_data = cur.fetchall()

    cur.execute("SELECT COUNT(*) AS total FROM fir")
    total_firs = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) AS total FROM fir WHERE status='open'")
    open_cases = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) AS total FROM officer")
    total_officers = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) AS total FROM citizen")
    total_citizens = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) AS total FROM officer_attendance WHERE status='Present'")
    present_officers = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) AS total FROM officer_attendance WHERE status='Sick Leave'")
    sick_leave = cur.fetchone()['total']

    cur.close(); conn.close()

    return render_template(
        'police_dashboard.html',
        crime_data=crime_data,
        total_firs=total_firs,
        open_cases=open_cases,
        total_officers=total_officers,
        total_citizens=total_citizens
    )

# ---------- ADD FIR ----------
@app.route('/add_fir', methods=['GET', 'POST'])
def add_fir():
    if 'username' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()

    try:
        # Fetch dropdowns
        cur.execute("SELECT crime_id, crime_type FROM crime")
        crimes = cur.fetchall()

        cur.execute("SELECT station_id, station_name FROM police_station")
        stations = cur.fetchall()

        if request.method == 'POST':
            citizen_name = request.form.get('citizen_name')
            citizen_phone = request.form.get('citizen_phone')
            citizen_address = request.form.get('citizen_address')
            city = request.form.get('city')
            crime_id = request.form.get('crime_id')
            station_id = request.form.get('station_id')
            status = request.form.get('status')

            # Validate all fields
            if not all([citizen_name, city, crime_id, station_id, status]):
                flash("Required fields missing!", "danger")
                return render_template('add_fir.html', crimes=crimes, stations=stations)

            # Convert IDs to integer
            crime_id = int(crime_id)
            station_id = int(station_id)

            # Insert citizen
            cur.execute(
                "INSERT INTO citizen (name, phone, address) VALUES (%s,%s,%s)",
                (citizen_name, citizen_phone, citizen_address)
            )
            citizen_id = cur.lastrowid

            if not citizen_id:
                flash("Failed to insert citizen. Check database.", "danger")
                return render_template('add_fir.html', crimes=crimes, stations=stations)

            # Insert FIR
            cur.execute(
                "INSERT INTO fir (citizen_id, crime_id, station_id, fir_date, status, city) "
                "VALUES (%s,%s,%s,CURDATE(),%s,%s)",
                (citizen_id, crime_id, station_id, status, city)
            )

            conn.commit()
            flash("FIR submitted successfully!", "success")
            return redirect('/view_fir')

    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")

    finally:
        cur.close()
        conn.close()

    return render_template('add_fir.html', crimes=crimes, stations=stations)
# ---------- VIEW FIR ----------
@app.route('/view_fir')
def view_fir():
    if 'username' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()

    search = request.args.get('search')

    if search:
        cur.execute("""
            SELECT f.fir_id, c.name AS citizen_name, cr.crime_type, f.status
            FROM fir f
            JOIN citizen c ON f.citizen_id = c.citizen_id
            JOIN crime cr ON f.crime_id = cr.crime_id
            WHERE c.name LIKE %s OR f.city LIKE %s
        """, ('%' + search + '%', '%' + search + '%'))
    else:
        cur.execute("""
            SELECT f.fir_id, c.name AS citizen_name, cr.crime_type, f.status
            FROM fir f
            JOIN citizen c ON f.citizen_id = c.citizen_id
            JOIN crime cr ON f.crime_id = cr.crime_id
        """)

    firs = cur.fetchall()
    cur.close(); conn.close()

    return render_template("view_fir.html", firs=firs)

# ---------- EDIT FIR ----------
@app.route('/edit_fir/<int:fir_id>', methods=['GET','POST'])
def edit_fir(fir_id):
    if 'username' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        cur.execute("UPDATE fir SET status=%s WHERE fir_id=%s",
                    (request.form['status'], fir_id))
        conn.commit()
        cur.close(); conn.close()
        return redirect('/view_fir')

    cur.execute("SELECT * FROM fir WHERE fir_id=%s", (fir_id,))
    fir = cur.fetchone()

    cur.close(); conn.close()
    return render_template('edit_fir.html', fir=fir)

# ---------- DELETE FIR ----------
@app.route('/delete_fir/<int:fir_id>')
def delete_fir(fir_id):
    if session.get('role') != 'ADMIN':
        return "Access Denied"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM fir WHERE fir_id=%s", (fir_id,))
    conn.commit()

    cur.close(); conn.close()
    return redirect('/view_fir')

# ---------- STORED PROCEDURE ----------
@app.route('/station_report')
def station_report():
    if 'username' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()

    try:
        # Station-wise total FIRs
        cur.execute("""
            SELECT ps.station_name, COUNT(f.fir_id) AS total_cases
            FROM fir f
            JOIN police_station ps ON f.station_id = ps.station_id
            GROUP BY ps.station_name
        """)
        station_data = cur.fetchall()

        # Open cases per station
        cur.execute("""
            SELECT ps.station_name, COUNT(f.fir_id) AS open_cases
            FROM fir f
            JOIN police_station ps ON f.station_id = ps.station_id
            WHERE f.status = 'open'
            GROUP BY ps.station_name
        """)
        open_data = cur.fetchall()

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        station_data = []
        open_data = []

    finally:
        cur.close()
        conn.close()

    return render_template(
        'station_report.html',
        station_data=station_data,
        open_data=open_data
    )

# ---------- CITIZEN REGISTER ----------
@app.route('/citizen_register', methods=['GET','POST'])
def citizen_register():
    if request.method == 'POST':
        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute("""
                INSERT INTO citizen (name, aadhar_no, phone, address, password)
                VALUES (%s,%s,%s,%s,%s)
            """, (request.form['name'], request.form['aadhar_no'],
                  request.form['phone'], request.form['address'],
                  generate_password_hash(request.form['password'])))

            conn.commit()
            flash("Registration successful", "success")
            return redirect('/citizen_login')

        except IntegrityError:
            conn.rollback()
            flash("Citizen already exists", "danger")

        finally:
            cur.close(); conn.close()

    return render_template('citizen_register.html')

# ---------- CITIZEN LOGIN ----------
@app.route('/citizen_login', methods=['GET','POST'])
def citizen_login():
    if request.method == 'POST':
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT citizen_id, name, password FROM citizen WHERE name=%s",
                    (request.form['username'],))
        user = cur.fetchone()
        cur.close(); conn.close()

        if user and check_password_hash(user['password'], request.form['password']):
            session['citizen_id'] = user['citizen_id']
            session['username'] = user['name']      # <-- add this
            session['role'] = 'citizen'             # <-- add this
            return redirect('/citizen_dashboard')

        flash("Invalid login credentials", "danger")

    return render_template('citizen_login.html')
# ---------- CITIZEN DASHBOARD ----------
@app.route('/citizen_dashboard')
def citizen_dashboard():
    if 'username' not in session or session.get('role') != 'citizen':
        return redirect('/citizen_login')

    conn = get_db()
    cur = conn.cursor()

    try:
        # Total stats
        cur.execute("SELECT COUNT(*) AS total FROM fir_requests WHERE citizen_name=%s", (session['username'],))
        total_firs = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) AS total FROM fir_requests WHERE citizen_name=%s AND status='Pending'", (session['username'],))
        pending_requests = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) AS total FROM fir_requests WHERE citizen_name=%s AND status='Approved'", (session['username'],))
        approved_requests = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) AS total FROM fir_requests WHERE citizen_name=%s AND status='Rejected'", (session['username'],))
        rejected_requests = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) AS total FROM citizen")
        total_citizens = cur.fetchone()['total']

        # Fetch FIR requests table
        cur.execute("SELECT * FROM fir_requests WHERE citizen_name=%s ORDER BY created_at DESC", (session['username'],))
        requests = cur.fetchall()

        # Fetch recent neighborhood complaints
        cur.execute("SELECT * FROM neighbourhood_complaints ORDER BY created_at DESC LIMIT 5")
        recent_complaints = cur.fetchall()

        # Fetch recent missing persons
        cur.execute("SELECT * FROM missing_persons ORDER BY created_at DESC LIMIT 5")
        recent_missing = cur.fetchall()

    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}", "danger")
        total_firs = pending_requests = approved_requests = rejected_requests = total_citizens = 0
        requests = recent_complaints = recent_missing = []
    finally:
        cur.close()
        conn.close()

    return render_template(
        'citizen_dashboard.html',
        total_firs=total_firs,
        pending_requests=pending_requests,
        approved_requests=approved_requests,
        rejected_requests=rejected_requests,
        total_citizens=total_citizens,
        requests=requests,
        recent_complaints=recent_complaints,
        recent_missing=recent_missing
    )

# ---------- OFFICER PROFILE ----------
@app.route('/officer_profile', methods=['GET','POST'])
def officer_profile():
    print("Session:", session)
    if 'officer_id' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        cur.execute("""
            UPDATE officer SET phone=%s, email=%s WHERE officer_id=%s
        """,(request.form['phone'], request.form['email'], session['officer_id']))
        conn.commit()

    cur.execute("SELECT * FROM officer WHERE officer_id=%s",(session['officer_id'],))
    officer = cur.fetchone()

    cur.close(); conn.close()
    return render_template("officer_profile.html", officer=officer)

# ---------- EMERGENCY ----------
@app.route('/add_emergency_call', methods=['GET','POST'])
def add_emergency_call():
    if 'username' not in session or session.get('role') != 'citizen':
        return redirect('/citizen_login')

    if request.method == 'POST':
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO emergency_calls (citizen_id, location, description)
            VALUES (%s,%s,%s)
        """,(session['citizen_id'], request.form['location'], request.form['description']))

        conn.commit()
        cur.close(); conn.close()

        flash("Emergency reported successfully!", "success")
        return redirect('/citizen_dashboard')

    return render_template("add_emergency_call.html")

@app.route('/view_emergency_calls')
def view_emergency_calls():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM emergency_calls ORDER BY call_time DESC")
    calls = cur.fetchall()

    cur.close(); conn.close()
    return render_template("view_emergency_calls.html", calls=calls)

@app.route('/emergency_logs')
def emergency_logs():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM emergency_log ORDER BY log_time DESC")
    logs = cur.fetchall()

    cur.close(); conn.close()
    return render_template("emergency_logs.html", logs=logs)

@app.route('/report_emergency', methods=['GET','POST'])
def report_emergency():
    if request.method == 'POST':
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO emergency_calls (citizen_id, location, description)
            VALUES (%s,%s,%s)
        """,(request.form['citizen_id'], request.form['location'], request.form['description']))

        conn.commit()
        cur.close(); conn.close()

        flash("Emergency reported successfully!", "success")
        return redirect('/citizen_dashboard')

    return render_template("report_emergency.html")

# ---------- LOGOUT ----------
@app.route('/citizen_logout')
def citizen_logout():
    session.pop('citizen_id', None)
    session.pop('username', None)
    session.pop('role', None)
    return redirect('/citizen_login')

@app.route('/test_ui')
def test_ui():
    return render_template('test_ui.html')
@app.route('/download_fir/<int:fir_id>')
def download_fir(fir_id):
    return f"Download FIR {fir_id}"  # later convert to PDF
@app.route('/missing_persons', methods=['GET', 'POST'])
def missing_persons():
    if 'username' not in session or session.get('role') != 'citizen':
        return redirect('/login')

    conn = get_db()
    cur = conn.cursor()

    try:
        if request.method == 'POST':
            name = request.form['name']
            city = request.form['city']
            status = request.form.get('status', 'Missing')
            reported_by = session['username']

            cur.execute("""
                INSERT INTO missing_persons (name, city, status, reported_by)
                VALUES (%s, %s, %s, %s)
            """, (name, city, status, reported_by))
            conn.commit()

            flash("Missing person report submitted successfully!", "success")
            return redirect('/missing_persons')

        cur.execute("""
            SELECT name, city, status
            FROM missing_persons
            ORDER BY created_at DESC
            LIMIT 5
        """)
        recent_missing = cur.fetchall()

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        recent_missing = []

    finally:
        cur.close()
        conn.close()

    return render_template('missing_persons.html', recent_missing=recent_missing)
@app.route('/neighbourhood_complaints', methods=['GET', 'POST'])
def neighbourhood_complaints():
    if 'username' not in session or session.get('role') != 'citizen':
        return redirect('/login')

    conn = get_db()
    cur = conn.cursor()

    try:
        if request.method == 'POST':
            citizen_name = request.form['citizen_name']
            city = request.form['city']
            complaint_text = request.form['complaint_text']

            cur.execute("""
                INSERT INTO neighbourhood_complaints 
                (citizen_name, city, complaint_text)
                VALUES (%s, %s, %s)
            """, (citizen_name, city, complaint_text))
            conn.commit()

            flash("Complaint submitted successfully!", "success")
            return redirect('/neighbourhood_complaints')

        # GET request
        cur.execute("""
            SELECT citizen_name, city, complaint_text, status
            FROM neighbourhood_complaints
            ORDER BY created_at DESC
            LIMIT 5
        """)
        recent_complaints = cur.fetchall()

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        recent_complaints = []

    finally:
        cur.close()
        conn.close()

    return render_template('neighbourhood_complaints.html', recent_complaints=recent_complaints)

@app.route('/request_fir', methods=['GET', 'POST'])
def request_fir():
    if 'username' not in session or session.get('role') != 'citizen':
        return redirect('/citizen_login')  # make sure it points to citizen login

    conn = get_db()
    cur = conn.cursor()

    try:
        if request.method == 'POST':
            # safely get form values
            name = session['username']
            phone = request.form.get('citizen_phone')
            address = request.form.get('citizen_address')
            crime = request.form.get('crime_type')
            city = request.form.get('city')

            # Validate required fields
            if not all([name, city, crime]):
                flash("Please fill in all required fields!", "danger")
                return render_template('request_fir.html')

            # Insert request
            cur.execute("""
                INSERT INTO fir_requests
                (citizen_name, phone, address, crime_type, city)
                VALUES (%s,%s,%s,%s,%s)
            """, (session['username'], phone, address, crime, city))
            conn.commit()
            flash("FIR request submitted. Police will review it.", "success")
            return redirect('/my_firs')  # redirect to track submitted FIRs

    except Exception as e:
        conn.rollback()
        flash(f"Error submitting FIR: {str(e)}", "danger")
        return render_template('request_fir.html')

    finally:
        cur.close()
        conn.close()

    return render_template('request_fir.html')


@app.route('/my_firs')
def my_firs():
    if 'username' not in session or session.get('role') != 'citizen':
        return redirect('/login')

    try:
        conn = get_db()
        cur = conn.cursor()

        username = session['username']

        cur.execute("""
            SELECT request_id, crime_type, city, status, created_at
            FROM fir_requests
            WHERE citizen_name=%s
            ORDER BY created_at DESC
        """, (username,))

        requests = cur.fetchall()

    except Exception as e:
        return f"Error: {str(e)}"   # TEMP DEBUG

    finally:
        cur.close()
        conn.close()

    return render_template('my_firs.html', requests=requests)
@app.route('/approve_request/<int:request_id>', methods=['POST'])
def approve_request(request_id):
    if 'username' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()

    decision = request.form['decision']

    cur.execute(
        "UPDATE fir_requests SET status=%s WHERE request_id=%s",
        (decision, request_id)
    )
    conn.commit()

    cur.close()
    conn.close()

    flash(f"Request {decision.lower()}", "success")
    return redirect('/pending_requests')
@app.route('/pending_requests')
def pending_requests():
    if 'username' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM fir_requests
        WHERE status='Pending'
        ORDER BY created_at DESC
    """)

    requests = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('pending_requests.html', requests=requests)
# ---------- RUN ----------
if __name__ == '__main__':
    app.run(debug=True)