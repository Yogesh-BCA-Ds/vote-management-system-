from flask import *
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import os
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "local-development-key"
)


# Database connection: Neon PostgreSQL
def get_db():
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is missing."
        )

    return psycopg.connect(
        database_url,
        row_factory=dict_row
    )


# Home page
@app.route("/")
def home_page():
    return render_template("index.html")


# Login
@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    with get_db() as conn:
        user = conn.execute("""
            SELECT user_id, role, password
            FROM newuser
            WHERE username = %s
            """, (username,)).fetchone()

        if not user:
            return "Invalid username or password", 401

        stored_password = user["password"]

        # Check whether the stored password is already hashed
        is_hashed = (
            stored_password.startswith("scrypt:")
            or stored_password.startswith("pbkdf2:")
        )

        if is_hashed:
            # Verify a previously hashed password
            password_valid = check_password_hash(
                stored_password,
                password
            )

        else:
            # TEMPORARY compatibility for existing plaintext passwords
            password_valid = (stored_password == password)

            if password_valid:
                # Upgrade the old password to a secure hash
                new_hash = generate_password_hash(password)

                conn.execute("""
                    UPDATE newuser
                    SET password = %s
                    WHERE user_id = %s
                    """, (new_hash, user["user_id"]))

        if not password_valid:
            return "Invalid username or password", 401

        user_id = user["user_id"]
        role = user["role"]

        # Clear any old session before logging in
        session.clear()

        session["user_id"] = user_id
        session["role"] = role

        conn.execute("""
            UPDATE newuser
            SET last_login = CURRENT_TIMESTAMP
            WHERE user_id = %s
            """, (user_id,))

        if role == "voter":
            voter_profile = conn.execute("""
                SELECT profile_id
                FROM voters
                WHERE user_id = %s
                """, (user_id,)).fetchone()

            if voter_profile:
                return redirect(url_for("voter_dashboard"))

            return render_template(
                "voter.html",
                username=username
            )

        if role == "admin":
            return render_template(
                "manager.html",
                username=username
            )

        if role == "candidate":
            return redirect(url_for("candidate"))

        return "Invalid role", 400


# Voter profile
@app.route("/voter", methods=["POST"])
def voter():
    user_id = session["user_id"]

    phone = request.form["phone"]
    city = request.form["city"]
    address = request.form["address"]
    state = request.form["state"]
    country = request.form["country"]

    with get_db() as conn:
        conn.execute("""
            INSERT INTO voters
                (user_id, phone, adress, city, state, country)
            VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                phone,
                address,
                city,
                state,
                country
            ))

    return render_template(
        "status.html",
        title="Profile Updated",
        message="Your voter profile has been saved successfully.",
        link_url=url_for("voter_dashboard"),
        link_text="Go to Dashboard"
    )


# Create election
@app.route("/admin", methods=["POST"])
def admin():
    title = request.form["title"]
    start_date = request.form["start_date"]
    end_date = request.form["end_date"]
    des = request.form["des"]
    elg = request.form["elg"]
    result_date = request.form.get("result_date", "")
    option = request.form["option"]

    start_date = datetime.strptime(
        start_date,
        "%Y-%m-%dT%H:%M"
    )

    end_date = datetime.strptime(
        end_date,
        "%Y-%m-%dT%H:%M"
    )

    if result_date:
        result_date = datetime.strptime(
            result_date,
            "%Y-%m-%dT%H:%M"
        )
    else:
        result_date = None

    now = datetime.utcnow() + timedelta(hours=5, minutes=30)

    if now < start_date:
        status = "upcoming"
    elif now <= end_date:
        status = "ongoing"
    else:
        status = "completed"

    with get_db() as conn:
        conn.execute("""
            INSERT INTO election
                (title, start_date, end_date, des, elg,
                 result_date, status, election_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                title,
                start_date,
                end_date,
                des,
                elg,
                result_date,
                status,
                option
            ))

    return render_template(
        "status.html",
        title="Election Created",
        message="The election has been created successfully",
        link_url=url_for("home_page"),
        link_text="Return to home"
    )


# Registration page
@app.route("/register")
def register_page():
    return render_template("register.html")


# Register user
@app.route("/register/data", methods=["POST"])
def data():
    first_name = request.form["first name"]
    last_name = request.form["last name"]
    username = request.form["username"]
    email = request.form["email"]
    password = request.form["password"]
    role = request.form["option"]

    # Hash the password before storing it
    hashed_password = generate_password_hash(password)

    with get_db() as conn:
        existing_user = conn.execute("""
            SELECT user_id
            FROM newuser
            WHERE username = %s
            """, (username,)).fetchone()

        if existing_user:
            return render_template(
                "register.html",
                error="Username already exists. Please choose another."
            )

        conn.execute("""
            INSERT INTO newuser
                (first_name, last_name, username, email, password, role)
            VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                first_name,
                last_name,
                username,
                email,
                hashed_password,
                role
            ))

    return render_template(
        "status.html",
        title="Registration Successful",
        message="Your account has been created successfully. You can now sign in.",
        link_url=url_for("home_page"),
        link_text="Sign In"
    )


# Candidate page
@app.route("/candidate", methods=["GET", "POST"])
def candidate():
    with get_db() as conn:

        if request.method == "GET":
            elections = conn.execute("""
                SELECT election_id, title
                FROM election
                ORDER BY election_id DESC
                """).fetchall()

            return render_template(
                "candidate.html",
                elections=elections
            )

        election_id = request.form["election_id"]
        name = request.form["name"]
        party = request.form["party"]
        manifesto = request.form["manifesto"]

        conn.execute("""
            INSERT INTO candidate
                (election_id, name, party, manifesto)
            VALUES (%s, %s, %s, %s)
            """, (
                election_id,
                name,
                party,
                manifesto
            ))

    return render_template(
        "status.html",
        title="Candidate added",
        message="The candidate has been added successfully.",
        link_url=url_for("candidate"),
        link_text="Add another candidate"
    )


# Voter dashboard
@app.route("/voter/dashboard")
def voter_dashboard():
    with get_db() as conn:
        elections = conn.execute("""
            SELECT *
            FROM election
            WHERE status = 'ongoing'
            """).fetchall()

    return render_template(
        "voter_dashboard.html",
        elections=elections
    )


# View election
@app.route("/view_election", methods=["POST"])
def view_election():
    election_id = request.form["election_id"]

    with get_db() as conn:
        election = conn.execute("""
            SELECT *
            FROM election
            WHERE election_id = %s
            """, (election_id,)).fetchone()

        candidates = conn.execute("""
            SELECT *
            FROM candidate
            WHERE election_id = %s
            """, (election_id,)).fetchall()

    return render_template(
        "view_election.html",
        election=election,
        candidates=candidates
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
