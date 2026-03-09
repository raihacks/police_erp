from flask import Flask, render_template, request, redirect, session, url_for,flash
from flask_mysqldb import MySQL
import MySQLdb.cursors
from werkzeug.security import generate_password_hash
from MySQLdb import IntegrityError


app = Flask(__name__)
app.secret_key = 'police_erp_secret'

# ---------- MySQL Configuration ----------
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'root123'
app.config['MYSQL_DB'] = 'police_erp'

mysql = MySQL(app)

# ---------- LOGIN ----------
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT role FROM users WHERE username=%s AND password=%s",
            (username, password)
        )
        user = cur.fetchone()
        cur.close()

        if user:
            session['role'] = user[0]
            session['username'] = username
            return redirect('/police_dashboard')

    return render_template('login.html')

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------- DASHBOARD ----------
@app.route('/police_dashboard')
def police_dashboard():

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Crime map data
    cur.execute("""
        SELECT city, latitude, longitude, COUNT(*) AS total_cases
        FROM fir
        GROUP BY city, latitude, longitude
    """)
    crime_data = cur.fetchall()

    # Total FIRs
    cur.execute("SELECT COUNT(*) AS total FROM fir")
    total_firs = cur.fetchone()['total']

    # Open cases
    cur.execute("SELECT COUNT(*) AS total FROM fir WHERE status='open'")
    open_cases = cur.fetchone()['total']

    # Total officers
    cur.execute("SELECT COUNT(*) AS total FROM officer")
    total_officers = cur.fetchone()['total']

    # Total citizens
    cur.execute("SELECT COUNT(*) AS total FROM citizen")
    total_citizens = cur.fetchone()['total']
    cur.execute("SELECT COUNT(*) AS total FROM officer_attendance WHERE status='Present'")
    present_officers = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) AS total FROM officer_attendance WHERE status='Sick Leave'")
    sick_leave = cur.fetchone()['total']

    cur.close()

    return render_template(
        'police_dashboard.html',
        crime_data=crime_data,
        total_firs=total_firs,
        open_cases=open_cases,
        total_officers=total_officers,
        total_citizens=total_citizens
    )

@app.route('/add_fir', methods=['GET', 'POST'])
def add_fir():
    if 'username' not in session:
        return redirect('/')

    cur = mysql.connection.cursor()

    # Dropdown data
    cur.execute("SELECT crime_id, crime_type FROM crime")
    crimes = cur.fetchall()

    cur.execute("SELECT station_id, station_name FROM police_station")
    stations = cur.fetchall()

    if request.method == 'POST':

        # Citizen data
        citizen_name = request.form['citizen_name']
        citizen_phone = request.form['citizen_phone']
        citizen_address = request.form['citizen_address']

        # FIR location
        city = request.form['city']

        # FIR data
        crime_id = request.form['crime_id']
        station_id = request.form['station_id']
        status = request.form['status']

        # Insert citizen (NO city column here)
        cur.execute(
            """
            INSERT INTO citizen (name, phone, address)
            VALUES (%s, %s, %s)
            """,
            (citizen_name, citizen_phone, citizen_address)
        )

        citizen_id = cur.lastrowid

        # Insert FIR
        cur.execute(
            """
            INSERT INTO fir
            (citizen_id, crime_id, station_id, fir_date, status, city)
            VALUES (%s, %s, %s, CURDATE(), %s, %s)
            """,
            (citizen_id, crime_id, station_id, status, city)
        )

        mysql.connection.commit()
        cur.close()

        return redirect('/view_fir')

    cur.close()

    return render_template(
        'add_fir.html',
        crimes=crimes,
        stations=stations
    )

# ---------- VIEW FIR ----------
@app.route('/view_fir')
def view_fir():
    if 'username' not in session:
        return redirect('/')

    search = request.args.get('search')

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if search:
        cur.execute("""
            SELECT 
                f.fir_id,
                c.name AS citizen_name,
                cr.crime_type,
                f.status
            FROM fir f
            JOIN citizen c ON f.citizen_id = c.citizen_id
            JOIN crime cr ON f.crime_id = cr.crime_id
            WHERE c.name LIKE %s OR f.city LIKE %s
        """, ('%' + search + '%', '%' + search + '%'))

    else:
        cur.execute("""
            SELECT 
                f.fir_id,
                c.name AS citizen_name,
                cr.crime_type,
                f.status
            FROM fir f
            JOIN citizen c ON f.citizen_id = c.citizen_id
            JOIN crime cr ON f.crime_id = cr.crime_id
        """)

    firs = cur.fetchall()
    cur.close()

    return render_template("view_fir.html", firs=firs)
# ---------- EDIT FIR ----------
@app.route('/edit_fir/<int:fir_id>', methods=['GET', 'POST'])
def edit_fir(fir_id):
    if 'username' not in session:
        return redirect('/')

    cur = mysql.connection.cursor()

    if request.method == 'POST':
        status = request.form['status']
        cur.execute(
            "UPDATE fir SET status=%s WHERE fir_id=%s",
            (status, fir_id)
        )
        mysql.connection.commit()
        cur.close()
        return redirect('/view_fir')

    cur.execute("SELECT * FROM fir WHERE fir_id=%s", (fir_id,))
    fir = cur.fetchone()
    cur.close()

    return render_template('edit_fir.html', fir=fir)

# ---------- DELETE FIR (ADMIN ONLY) ----------
@app.route('/delete_fir/<int:fir_id>')
def delete_fir(fir_id):
    if session.get('role') != 'ADMIN':
        return "Access Denied"

    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM fir WHERE fir_id=%s", (fir_id,))
    mysql.connection.commit()
    cur.close()

    return redirect('/view_fir')

# ---------- STORED PROCEDURE REPORT ----------
@app.route('/station_report')
def station_report():
    if 'username' not in session:
        return redirect('/')

    cur = mysql.connection.cursor()
    cur.callproc('get_station_case_count')
    data = cur.fetchall()
    cur.close()

    return render_template('report.html', data=data)
from werkzeug.security import generate_password_hash
from flask import flash

@app.route('/citizen_register', methods=['GET', 'POST'])
def citizen_register():
    if request.method == 'POST':
        name = request.form['name']
        aadhar = request.form['aadhar_no']
        phone = request.form['phone']
        address = request.form['address']
        password = generate_password_hash(request.form['password'])

        cursor = mysql.connection.cursor()

        try:
            # Insert into citizen table
            cursor.execute("""
                INSERT INTO citizen (name, aadhar_no, phone, address)
                VALUES (%s, %s, %s, %s)
            """, (name, aadhar, phone, address))

            citizen_id = cursor.lastrowid

            # Insert into login table
            cursor.execute("""
                INSERT INTO citizen_users (citizen_id, username, password_hash)
                VALUES (%s, %s, %s)
            """, (citizen_id, aadhar, password))

            mysql.connection.commit()
            flash("Registration successful. Please login.", "success")
            return redirect('/citizen_login')

        except Exception:
            mysql.connection.rollback()
            flash("Citizen already exists.", "danger")

        finally:
            cursor.close()

    return render_template('citizen_register.html')



from werkzeug.security import check_password_hash

@app.route('/citizen_login', methods=['GET', 'POST'])
def citizen_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute("""
            SELECT password_hash FROM citizen_users WHERE username = %s
        """, (username,))

        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user[0], password):
            return redirect('/citizen_dashboard')
        else:
            flash("Invalid login credentials", "danger")

    return render_template('citizen_login.html')

@app.route('/citizen_dashboard')
def citizen_dashboard():

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Total FIRs
    cur.execute("SELECT COUNT(*) AS total FROM fir")
    total_firs = cur.fetchone()['total']

    # Open Cases
    cur.execute("SELECT COUNT(*) AS total FROM fir WHERE status='Open'")
    open_cases = cur.fetchone()['total']

    # Closed Cases
    cur.execute("SELECT COUNT(*) AS total FROM fir WHERE status='Closed'")
    closed_cases = cur.fetchone()['total']

    # Under Investigation
    cur.execute("SELECT COUNT(*) AS total FROM fir WHERE status='Under Investigation'")
    investigation_cases = cur.fetchone()['total']

    # Officers
    cur.execute("SELECT COUNT(*) AS total FROM officer")
    total_officers = cur.fetchone()['total']

    # Citizens
    cur.execute("SELECT COUNT(*) AS total FROM citizen_users")
    total_citizens = cur.fetchone()['total']

    cur.close()

    return render_template(
        'citizen_dashboard.html',
        total_firs=total_firs,
        open_cases=open_cases,
        closed_cases=closed_cases,
        investigation_cases=investigation_cases,
        total_officers=total_officers,
        total_citizens=total_citizens
    )


@app.route('/officer_profile', methods=['GET', 'POST'])
def officer_profile():

    if 'username' not in session:
        return redirect('/')

    username = session['username']
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == 'POST':

        phone = request.form['phone']
        email = request.form['email']

        cur.execute("""
            UPDATE officer
            SET phone=%s, email=%s
            WHERE username=%s
        """, (phone, email, username))

        mysql.connection.commit()

    # Get officer info
    cur.execute("SELECT * FROM officer WHERE username=%s", (username,))
    officer = cur.fetchone()

    cur.close()

    return render_template("officer_profile.html", officer=officer)
@app.route('/citizen_logout')
def citizen_logout():
    session.clear()
    return redirect('/citizen_login')

@app.route('/test_ui')
def test_ui():
    return render_template('test_ui.html')

# ---------- RUN ----------
if __name__ == '__main__':
    app.run(debug=True)
