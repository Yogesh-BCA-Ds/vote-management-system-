import click
from getpass import getpass 
from werkzeug.security import generate_password_hash

def create_initial_owner(get_db):
    """Create the one designated owner from the local terminal."""

    conn = get_db()

    try:
        existing_owner = conn.execute("""
            SELECT user_id
            FROM newuser
            WHERE is_owner = 1
            LIMIT 1
        """).fetchone()

        if existing_owner:
            click.echo("An owner already exists. Setup cancelled.")
            return

        username = input("Owner username: ").strip()
        email = input("Owner email: ").strip()
        first_name = input("Owner first name: ").strip()
        last_name = input("Owner last name: ").strip()

        if not all([username, email, first_name, last_name]):
            click.echo("All fields are required.")
            return

        password = getpass("Owner password (minimum 12 characters): ")
        confirm = getpass("Confirm owner password: ")

        if len(password) < 12:
            click.echo("Password must be at least 12 characters.")
            return

        if password != confirm:
            click.echo("Passwords do not match.")
            return

        duplicate = conn.execute("""
            SELECT user_id
            FROM newuser
            WHERE username = ? OR email = ?
        """, (username, email)).fetchone()

        if duplicate:
            click.echo("That username or email is already registered.")
            return

        conn.execute("""
            INSERT INTO newuser (
                username, password, email,
                first_name, last_name, role,
                is_verified, application_status, is_owner
            )
            VALUES (?, ?, ?, ?, ?, 'admin', 1, 'approved', 1)
        """, (
            username,
            generate_password_hash(password),
            email,
            first_name,
            last_name
        ))

        conn.commit()
        click.echo("Owner account created successfully.")

    finally:
        conn.close()
