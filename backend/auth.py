from functools import wraps
from flask import session, abort


def approved_required(get_db):
    def decorator(*allowed_roles):
        def wrapper(view_function):
            @wraps(view_function)
            def wrapped(*args, **kwargs):
                user_id = session.get("user_id")

                if not user_id:
                    abort(401, description="Please sign in first.")

                conn = get_db()
                try:
                    user = conn.execute("""
                        SELECT user_id, role, is_verified,
                               application_status, is_owner
                        FROM newuser
                        WHERE user_id = ?
                    """, (user_id,)).fetchone()
                finally:
                    conn.close()

                if not user:
                    session.clear()
                    abort(401, description="Account not found.")

                if (user["application_status"] != "approved"
                        or user["is_verified"] != 1):
                    session.clear()
                    abort(403, description="Your account is not approved.")

                if user["role"] not in allowed_roles:
                    abort(403, description="You are not allowed to access this feature.")

                if user["role"] == "admin" and user["is_owner"] != 1:
                    abort(403, description="Owner access required.")

                return view_function(*args, **kwargs)
            return wrapped
        return wrapper
    return decorator
    
def owner_required(get_db):
    def decorator(view_function):
        @wraps(view_function)
        def wrapped(*args, **kwargs):
            user_id = session.get("user_id")

            if not user_id:
                abort(401, description="Please sign in first.")

            conn = get_db()

            try:
                owner = conn.execute("""
                    SELECT user_id
                    FROM newuser
                    WHERE user_id = ?
                      AND role = 'admin'
                      AND is_owner = 1
                      AND is_verified = 1
                      AND application_status = 'approved'
                """, (user_id,)).fetchone()
            finally:
                conn.close()

            if not owner:
                abort(403, description="Only the designated owner can do this.")

            return view_function(*args, **kwargs)

        return wrapped
    return decorator
