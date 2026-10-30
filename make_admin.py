"""Give or take away admin rights.

Run:  python make_admin.py you@example.com            make this account an admin
      python make_admin.py you@example.com --remove   back to a normal renter account

The person must have signed up first (Sign up page, with the email code). Then log in on the normal Log in page:
admins get an extra "Admin" page in the menu. Nobody can make themselves admin from the website.
"""
import sys

import auth


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    role = "renter" if "--remove" in sys.argv else auth.ADMIN
    if auth.set_role(args[0], role):
        print(f"{auth.normalize_email(args[0])} is now: {auth.ROLE_LABELS[role]}. Log out and log in again to see the change.")
    else:
        sys.exit(f"No account with the email {args[0]}. Sign up first, then run this again.")


if __name__ == "__main__":
    main()
