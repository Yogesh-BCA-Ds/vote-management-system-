from flask import *
from datetime import datetime,timedelta
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
            
@app.route("/voter", methods=["POST"])
@approved_required("voter")
def voter():

    user_id = session["user_id"]

    # Get form values safely
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    city = request.form.get("city", "").strip()
    state = request.form.get("state", "").strip()
    country = request.form.get("country", "").strip()

    # Helper for displaying validation errors
    def validation_error(message):
        return render_template(
            "voter.html",
            username=session.get("username", "Voter"),
            error=message
        ), 400

    # 1. Required field validation
    if not all([phone, address, city, state, country]):
        return validation_error("Please complete all required fields.")

    # 2. Phone validation
    phone_digits = re.sub(r"\D", "", phone)

    if (
        not re.fullmatch(r"\+?[0-9][0-9\s()-]*", phone)
        or len(phone_digits) < 7
        or len(phone_digits) > 15
    ):
        return validation_error(
            "Enter a valid phone number containing 7 to 15 digits."
        )

    # 3. Address validation
    if (
        len(address) < 5
        or len(address) > 200
        or not any(char.isalnum() for char in address)
    ):
        return validation_error(
            "Address must be between 5 and 200 characters."
        )

    # 4. City validation
    if (
        len(city) < 2
        or len(city) > 80
        or not city[0].isalpha()
        or not all(
            char.isalpha() or char in " .'-"
            for char in city
        )
    ):
        return validation_error("Please enter a valid city name.")

    # 5. State validation
    allowed_states = {
        "Andhra Pradesh",
        "Arunachal Pradesh",
        "Assam",
        "Bihar",
        "Chhattisgarh",
        "Goa",
        "Gujarat",
        "Haryana",
        "Himachal Pradesh",
        "Jharkhand",
        "Karnataka",
        "Kerala",
        "Madhya Pradesh",
        "Maharashtra",
        "Manipur",
        "Meghalaya",
        "Mizoram",
        "Nagaland",
        "Odisha",
        "Punjab",
        "Rajasthan",
        "Sikkim",
        "Tamil Nadu",
        "Telangana",
        "Tripura",
        "Uttar Pradesh",
        "Uttarakhand",
        "West Bengal"
    }

    if state not in allowed_states:
        return validation_error("Please select a valid Indian state.")

    # 6. Country validation
    if (
        len(country) < 2
        or len(country) > 56
        or not country[0].isalpha()
        or not all(
            char.isalpha() or char in " .'-"
            for char in country
        )
    ):
        return validation_error("Please enter a valid country name.")

    # 7. Save voter profile
    conn = sqlite3.connect("database/vote_man.db")

    try:
        conn.execute("""
            INSERT INTO voters (
                user_id,
                phone,
                adress,
                city,
                state,
                country
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            phone,
            address,
            city,
            state,
            country
        ))

        conn.commit()

    except sqlite3.IntegrityError:
        conn.rollback()
        return validation_error(
            "A voter profile may already exist for this account."
        )

    except sqlite3.Error:
        conn.rollback()
        return validation_error(
            "Unable to save your profile due to a database error."
        )

    finally:
        conn.close()

    return render_template(
        "status.html",
        title="Profile Updated",
        message="Your voter profile has been saved successfully.",
        link_url=url_for("voter_dashboard"),
        link_text="Go to Dashboard"
    )
    
@app.route("/admin", methods=["POST"])
@owner_required
def admin():

    # Get form values safely
    title = request.form.get("title", "").strip()
    des = request.form.get("des", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    result_date = request.form.get("result_date", "").strip()
    option = request.form.get("option", "").strip().lower()
    regions = request.form.getlist("elg")

    # Helper to display backend validation errors
    def validation_error(message):
        return render_template(
            "admin.html",
            username=session.get("username", "Owner"),
            error=message
        ), 400

    # 1. Required field validation
    if not all([title, des, start_date, end_date, result_date, option]):
        return validation_error("Please complete all required fields.")

    if not regions:
        return validation_error("Please select at least one eligible region.")

    # 2. Title validation
    if len(title) < 3 or len(title) > 120:
        return validation_error(
            "Election title must contain 3 to 120 characters."
        )

    # 3. Description validation
    if len(des) < 10 or len(des) > 2000:
        return validation_error(
            "Description must contain 10 to 2000 characters."
        )

    # 4. Election type validation
    allowed_types = ("local", "state", "national", "org")

    if option not in allowed_types:
        return validation_error("Please select a valid election type.")

    # 5. Eligible region validation
    allowed_regions = {
        "all",
        "andhra_pradesh",
        "arunachal_pradesh",
        "assam",
        "bihar",
        "chhattisgarh",
        "goa",
        "gujarat",
        "haryana",
        "himachal_pradesh",
        "jharkhand",
        "karnataka",
        "kerala",
        "madhya_pradesh",
        "maharashtra",
        "manipur",
        "meghalaya",
        "mizoram",
        "nagaland",
        "odisha",
        "punjab",
        "rajasthan",
        "sikkim",
        "tamil_nadu",
        "telangana",
        "tripura",
        "uttar_pradesh",
        "uttarakhand",
        "west_bengal"
    }

    # Reject invalid or manipulated region values
    if not set(regions).issubset(allowed_regions):
        return validation_error("One or more selected regions are invalid.")

    # All India must be selected alone
    if "all" in regions and len(regions) > 1:
        return validation_error(
            "All India cannot be selected together with individual states."
        )

    # Store multiple selected regions in the existing text column
    if "all" in regions:
        elg = "all"
    else:
        elg = ",".join(regions)

    # 6. Date validation
    try:
        start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M")
        end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M")
        result_date = datetime.strptime(result_date, "%Y-%m-%dT%H:%M")

    except ValueError:
        return validation_error("Please enter valid election dates and times.")

    # 7. Date order validation
    if start_date >= end_date:
        return validation_error(
            "Election end date and time must be after the start date and time."
        )

    if result_date < end_date:
        return validation_error(
            "Result date and time cannot be before the election end date and time."
        )

    # 8. Calculate current time in India (IST, UTC+5:30)
    # This avoids comparing Indian form dates with a UTC server clock.
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)

    # 9. Determine election status
    if now < start_date:
        status = "upcoming"

    elif now < end_date:
        status = "ongoing"

    else:
        status = "completed"

    # 10. Insert election into database
    conn = sqlite3.connect("database/vote_man.db")

    try:
        conn.execute("""
            INSERT INTO election (
                title,
                start_date,
                end_date,
                des,
                elg,
                result_date,
                status,
                election_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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

        conn.commit()

    except sqlite3.Error:
        conn.rollback()
        return validation_error(
            "The election could not be created because of a database error."
        )

    finally:
        conn.close()

    return render_template(
        "status.html",
        title="Election Created",
        message="The election has been created successfully",
        link_url=url_for("home_page"),
        link_text="Return to home"
    )
    
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

    # Name validation
    for name in (first_name, last_name):
        if (len(name) > 50 or not all(char.isalpha() or char in " '-" for char in name)):
            return render_template(
            "register.html",
            error="Please enter a valid name."
        ), 400

    # Username validation
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.]{2,29}", username):
        return render_template(
        "register.html",
        error="Username must be 3–30 characters and contain only letters, numbers, dots or underscores."
    ), 400

    # Email validation
    if (len(email) > 254or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+",
        email)):
        return render_template(
        "register.html",
        error="Please enter a valid email address."
    ), 400
    
    if len(password) < 8 or len(password) > 128:
        return render_template(
            "register.html",
            error="Password must be between 8 and 128 characters."
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
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    now_text = now.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
    UPDATE election
    SET status = CASE
        WHEN start_date > ? THEN 'upcoming'
        WHEN end_date > ? THEN 'ongoing'
        ELSE 'completed'
    END
    """, (now_text, now_text))

    conn.commit()
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



