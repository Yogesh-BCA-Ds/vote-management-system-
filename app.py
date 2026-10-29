from flask import *
from datetime import datetime
from getpass import getpass
from backend.owner_setup import create_initial_owner
from backend.auth import approved_required, owner_required
from dotenv import load_dotenv
import os
import sqlite3
import re
import click

from werkzeug.security import generate_password_hash,check_password_hash
from dotenv import load_dotenv 

app = Flask(__name__)
load_dotenv()
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")
if not app.config["SECRET_KEY"]:
    raise RuntimeError("set the FLASK_SECRET_KEY environment variable before starting the app")

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)),"database","vote_man.db")

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

approved_required = approved_required(get_db)
owner_required = owner_required(get_db)

@app.cli.command("create-owner")
def create_owner():
    create_initial_owner(get_db)
    
@app.route("/")
def home_page():
    return render_template("home_page.html")

@app.route("/login", methods=["POST","GET"])
def login():
    if request.method == "GET":
        return render_template("index.html")
        
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    conn = get_db()

    try:
        user = conn.execute("""
            SELECT user_id, username, password, role,
                   is_verified, application_status, is_owner
            FROM newuser
            WHERE username = ?
        """, (username,)).fetchone()

        if not user:
            return render_template(
                "index.html",
                error="Invalid username or password."
            ), 401

        stored_password = user["password"]

        # Support old plaintext passwords during transition.
        # New passwords must always be hashed.
        try:
            password_matches = check_password_hash(
                stored_password, password
            )
        except (ValueError, TypeError):
            password_matches = False

        if not password_matches and stored_password == password:
            password_matches = True
            conn.execute("""
                UPDATE newuser
                SET password = ?
                WHERE user_id = ?
            """, (
                generate_password_hash(password),
                user["user_id"]
            ))
            conn.commit()

        if not password_matches:
            return render_template(
                "index.html",
                error="Invalid username or password."
            ), 401

        # Only the designated owner may use the admin account.
        if user["role"] == "admin" and user["is_owner"] != 1:
            return render_template(
                "index.html",
                error="This admin account is not the designated owner."
            ), 403

        if user["application_status"] == "rejected":
            return render_template(
                "index.html",
                error="Your application was rejected. Please contact the owner."
            ), 403
            
        if (user["application_status"] != "approved" or user["is_verified"] != 1):
            return render_template("index.html",error = "your application is pending approval. please try again later"),403

        session.clear()
        session["user_id"] = user["user_id"]
        session["role"] = user["role"]
        conn.execute("""
            UPDATE newuser
            SET last_login = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (user["user_id"],))
        conn.commit()

        if user["role"] == "voter":
            profile = conn.execute("""
                SELECT profile_id, is_active
                FROM voters
                WHERE user_id = ?
            """, (user["user_id"],)).fetchone()

            if not profile:
                return render_template(
                    "voter.html",
                    username=user["username"]
                )

            if profile["is_active"] != 1:
                session.clear()
                return render_template(
                    "index.html",
                    error="Your voter profile is inactive. Contact the owner."
                ), 403

            return redirect(url_for("voter_dashboard"))

        if user["role"] == "admin":
            return redirect(url_for("manager"))

        if user["role"] == "candidate":
            return redirect(url_for("candidate"))

        session.clear()
        return render_template(
            "index.html",
            error="This account has an invalid role."
        ), 403

    finally:
        conn.close()

@app.route("/manager")
@owner_required
def manager():
    conn = get_db()
    try:
        user = conn.execute("""
            SELECT username FROM newuser
            WHERE user_id = ?
        """, (session["user_id"],)).fetchone()
    finally:
        conn.close()

    return render_template("manager.html", username=user["username"])
            
@app.route("/voter",methods=["POST"])
@approved_required("voter")
def voter():
    user_id = session['user_id']
    phone = request.form["phone"]
    city = request.form["city"]
    address = request.form["address"]
    state = request.form["state"]
    country = request.form["country"]
    conn = sqlite3.connect("database/vote_man.db")
    conn.execute("""
    INSERT INTO voters (user_id, phone, adress, city, state, country)
    VALUES (?, ?, ?, ?, ?, ?)""", (user_id, phone, address, city, state, country))
    conn.commit()
    conn.close()
    return render_template("status.html",title="Profile Updated",
                            message="your voter profile has been saved successfully.",
                            link_url=url_for("voter_dashboard"),
                            link_text="Go to Dashboard")

@app.route("/admin",methods=['POST'])
@owner_required
def admin():
    conn = sqlite3.connect("database/vote_man.db")
    title = request.form['title']
    start_date = request.form['start_date']
    end_date = request.form['end_date']
    des = request.form['des']
    elg = request.form['elg']
    result_date = request.form['result_date']
    start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
    end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M")
    option = request.form['option']
    now = datetime.now()
    status = ""
    if now < start_date:
        status = "upcoming"
    elif now <= end_date:
        status = "ongoing"
    else:
        status = "completed"
    conn.execute("insert into election(title,start_date,end_date,des,elg,result_date,status,election_type) values (?,?,?,?,?,?,?,?)",
                     (title,start_date,end_date,des,elg,result_date,status,option))
    conn.commit()
    conn.close()
    return render_template("status.html",
                            title = "Election Created",
                            message = "The election has been created successfully",
                            link_url = url_for("home_page"),
                            link_text = "Return to home")

@app.route("/register")
def register_page():
    return render_template("register.html")

@app.route("/register/data", methods=["POST"])
def data():
    first_name = request.form.get("first name", "").strip()
    last_name = request.form.get("last name", "").strip()
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("option", "").strip().lower()

    if role not in ("voter", "candidate"):
        return render_template(
            "register.html",
            error="You can register only as a voter or candidate."
        ), 400

    if not all([first_name, last_name, username, email, password]):
        return render_template(
            "register.html",
            error="Please complete all required fields."
        ), 400

    if len(password) < 8:
        return render_template(
            "register.html",
            error="Password must be at least 8 characters."
        ), 400

    conn = get_db()

    try:
        existing = conn.execute("""
            SELECT user_id
            FROM newuser
            WHERE username = ? OR email = ?
        """, (username, email)).fetchone()

        if existing:
            return render_template(
                "register.html",
                error="That username or email is already registered."
            ), 400

        conn.execute("""
            INSERT INTO newuser (
                first_name, last_name, username,
                email, password, role,
                is_verified, application_status, is_owner
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, 'pending', 0)
        """, (
            first_name,
            last_name,
            username,
            email,
            generate_password_hash(password),
            role
        ))

        conn.commit()

    finally:
        conn.close()

    return render_template(
        "status.html",
        title="Application Submitted",
        message=(
            "Your account application has been submitted. "
            "You can sign in after the owner approves it."
        ),
        link_url=url_for("home_page"),
        link_text="Return to sign in"
    )
@app.route("/candidate", methods=["GET", "POST"])
@approved_required("candidate")
def candidate():
    conn = sqlite3.connect("database/vote_man.db")
    conn.row_factory = sqlite3.Row

    if request.method == "GET":

        elections = conn.execute("""
            SELECT election_id, title
            FROM election
            ORDER BY election_id DESC
        """).fetchall()

        conn.close()

        return render_template(
            "candidate.html",
            elections=elections
        )

    election_id = request.form["election_id"]
    name = request.form["name"]
    party = request.form["party"]
    manifesto = request.form["manifesto"]

    
    # Remove unnecessary whitespace
    name = name.strip()
    party = party.strip()
    manifesto = manifesto.strip()

    # 1. Validate required fields
    if not election_id.strip() or not name:
        conn.close()
        return render_template("candidate.html",
        elections=elections,
        error="Election and candidate name are required."), 400

    # 2. Validate candidate name
    if len(name) < 2 or len(name) > 80:
        conn.close()
        return render_template("candidate.html",
        elections=elections,
        error = "Candidate name must be 2–80 characters."), 400

    if not re.fullmatch(r"[^\W\d_][\w\s.'’-]*", name, re.UNICODE):
        conn.close()
        return render_template("candidate.html",
        elections=elections,
        error="Candidate name contains invalid characters."), 400

    # 3. Validate party/group (optional)
    if len(party) > 80:
        conn.close()
        return render_template("candidate.html",
        elections=elections,
        error="Party/group cannot exceed 80 characters."), 400

    if party and not re.fullmatch(r"[\w\s&.,'’()/-]+", party, re.UNICODE):
        conn.close()
        return render_template("candidate.html",
        elections=elections,
        error="Party/group contains invalid characters."), 400

    # 4. Validate manifesto (optional)
    if len(manifesto) > 1000:
        conn.close()
        return render_template("candidate.html",
        elections=elections,
        error="Manifesto cannot exceed 1000 characters."), 400

    election = conn.execute(
    "SELECT election_id FROM election WHERE election_id = ?",(election_id,)).fetchone()

    if election is None:
        conn.close()
        
        return render_template("candidate.html",
        elections=elections,
        error="Selected election does not exist."), 400
    conn.execute("""
        INSERT INTO candidate
        (election_id, name, party, manifesto)
        VALUES (?, ?, ?, ?)
    """, (
        election_id,
        name,
        party,
        manifesto
    ))

    conn.commit()
    conn.close()

    return render_template("status.html",
                           title = "Candidate added",
                           message = "The candidate has been added successfully.",
                           link_url = url_for("candidate"),
                           link_text = "add another candidate")

@app.route("/voter/dashboard")
@approved_required("voter")
def voter_dashboard():
    conn = get_db()

    try:
        profile = conn.execute("""
            SELECT is_active
            FROM voters
            WHERE user_id = ?
        """, (session["user_id"],)).fetchone()

        if not profile or profile["is_active"] != 1:
            abort(403, description="An active voter profile is required.")

        elections = conn.execute("""
            SELECT *
            FROM election
            WHERE status = 'ongoing'
        """).fetchall()

    finally:
        conn.close()

    return render_template(
        "voter_dashboard.html",
        elections=elections
    )
    
@app.route("/view_election", methods=["POST"])
@approved_required("voter")
def view_election():

    election_id = request.form["election_id"]

    conn = sqlite3.connect("database/vote_man.db")
    conn.row_factory = sqlite3.Row

    election = conn.execute("""
        SELECT *
        FROM election
        WHERE election_id = ?
    """, (election_id,)).fetchone()

    candidates = conn.execute("""
        SELECT *
        FROM candidate
        WHERE election_id = ?
    """, (election_id,)).fetchall()

    conn.close()

    return render_template(
        "view_election.html",
        election=election,
        candidates=candidates
    )

@app.route("/owner/applications")
@owner_required
def applications():
    conn = get_db()

    try:
        rows = conn.execute("""
            SELECT user_id, first_name, last_name, username,
                   email, role, date_joined, application_status
            FROM newuser
            WHERE role IN ('voter', 'candidate')
            ORDER BY
                CASE application_status
                    WHEN 'pending' THEN 0
                    WHEN 'approved' THEN 1
                    ELSE 2
                END,
                date_joined DESC
        """).fetchall()
    finally:
        conn.close()

    return render_template("application.html", applications=rows)


@app.route("/owner/applications/<int:user_id>/review", methods=["POST"])
@owner_required
def review_application(user_id):
    action = request.form.get("action", "").strip().lower()

    if action not in ("approve", "reject"):
        abort(400, description="Invalid review action.")

    conn = get_db()

    try:
        applicant = conn.execute("""
            SELECT user_id, role, application_status
            FROM newuser
            WHERE user_id = ?
              AND role IN ('voter', 'candidate')
        """, (user_id,)).fetchone()

        if not applicant:
            abort(404, description="Application not found.")

        if applicant["application_status"] != "pending":
            abort(400, description="This application has already been reviewed.")

        if action == "approve":
            conn.execute("""
                UPDATE newuser
                SET application_status = 'approved',
                    is_verified = 1
                WHERE user_id = ?
            """, (user_id,))

            if applicant["role"] == "voter":
                conn.execute("""
                    UPDATE voters
                    SET is_active = 1
                    WHERE user_id = ?
                """, (user_id,))

        else:
            conn.execute("""
                UPDATE newuser
                SET application_status = 'rejected',
                    is_verified = 0
                WHERE user_id = ?
            """, (user_id,))

            if applicant["role"] == "voter":
                conn.execute("""
                    UPDATE voters
                    SET is_active = 0
                    WHERE user_id = ?
                """, (user_id,))

        conn.commit()

    finally:
        conn.close()

    return redirect(url_for("applications"))

if __name__ == '__main__':
    app.run(debug=True)



