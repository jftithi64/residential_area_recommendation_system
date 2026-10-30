"""Delete one account so the same email / mobile can sign up again.

Run:  python delete_user.py name@example.com      (one account)
      python delete_user.py --all                  (every account except the administrator, and all reviews)
Removes the account, its review, its interests and any waiting email code. Listings are NOT touched.
The administrator account cannot be deleted here.
"""
import sys

import auth
import db


def delete_user(email):
    """Returns a short text saying what happened."""
    email = auth.normalize_email(email)
    with db.connect() as con:
        con.executescript(auth.DDL + ";" + auth.OTP_DDL + ";" + auth.INTEREST_DDL)
        row = con.execute("SELECT user_id, role FROM users WHERE email=?", (email,)).fetchone()
        if not row:
            con.execute("DELETE FROM email_otps WHERE email=?", (email,))
            return f"No account with {email}. (Any waiting code for it was cleared.)"
        if row[1] == auth.ADMIN:
            return "That is the administrator account. It is not deleted here."
        uid = row[0]
        con.execute("DELETE FROM reviews WHERE user_id=?", (uid,))
        con.execute("DELETE FROM user_interests WHERE user_id=?", (uid,))
        con.execute("DELETE FROM email_otps WHERE email=?", (email,))
        con.execute("DELETE FROM users WHERE user_id=?", (uid,))
    return f"Deleted the account {email}. You can sign up with it again."


def delete_all_users():
    """Every account except administrators, plus all reviews, interests and waiting codes."""
    with db.connect() as con:
        con.executescript(auth.DDL + ";" + auth.OTP_DDL + ";" + auth.INTEREST_DDL)
        n = con.execute("SELECT COUNT(*) FROM users WHERE role<>?", (auth.ADMIN,)).fetchone()[0]
        con.execute("DELETE FROM users WHERE role<>?", (auth.ADMIN,))
        con.execute("DELETE FROM user_interests WHERE user_id NOT IN (SELECT user_id FROM users)")
        con.execute("DELETE FROM reviews")
        con.execute("DELETE FROM email_otps")
    return f"Deleted {n} account(s) and all reviews. The administrator account is kept."


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Use:  python delete_user.py name@example.com     or     python delete_user.py --all")
        sys.exit(1)
    print(delete_all_users() if sys.argv[1] == "--all" else delete_user(sys.argv[1]))
