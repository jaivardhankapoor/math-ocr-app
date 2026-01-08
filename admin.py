#!/usr/bin/env python3
"""Admin CLI for user management"""

import argparse
import sys
from tabulate import tabulate

import database


def set_tier(email: str, tier: str):
    """Set user tier by email"""
    if tier not in ("free", "paid", "unlimited"):
        print(f"Error: Invalid tier '{tier}'. Must be 'free', 'paid', or 'unlimited'")
        sys.exit(1)

    user = database.get_user_by_email(email)
    if not user:
        print(f"Error: User '{email}' not found")
        sys.exit(1)

    database.update_user_tier(user["id"], tier)
    print(f"✓ Updated {email} to tier: {tier}")


def list_users():
    """List all users"""
    database.init_db()
    users = database.list_users(limit=1000)

    if not users:
        print("No users found")
        return

    table = []
    for user in users:
        table.append([
            user["email"],
            user["name"] or "",
            user["tier"],
            user["stripe_customer_id"] or "-",
            user["created_at"],
        ])

    print(tabulate(
        table,
        headers=["Email", "Name", "Tier", "Stripe Customer", "Created"],
        tablefmt="grid"
    ))
    print(f"\nTotal: {len(users)} users")


def user_info(email: str):
    """Show detailed user info"""
    database.init_db()
    user = database.get_user_by_email(email)

    if not user:
        print(f"Error: User '{email}' not found")
        sys.exit(1)

    # Get job count
    job_count_24h = database.get_user_job_count_24h(user["id"])
    total_jobs = len(database.list_jobs(limit=10000, user_id=user["id"]))

    print("\n=== User Info ===")
    print(f"ID:                    {user['id']}")
    print(f"Email:                 {user['email']}")
    print(f"Name:                  {user['name'] or '(none)'}")
    print(f"Tier:                  {user['tier']}")
    print(f"Stripe Customer ID:    {user['stripe_customer_id'] or '(none)'}")
    print(f"Stripe Subscription:   {user['stripe_subscription_id'] or '(none)'}")
    print(f"Created:               {user['created_at']}")
    print(f"\nUsage:")
    print(f"  Jobs (last 24h):     {job_count_24h}")
    print(f"  Jobs (total):        {total_jobs}")


def main():
    database.init_db()

    parser = argparse.ArgumentParser(description="Admin CLI for Math OCR")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # set-tier command
    set_tier_parser = subparsers.add_parser("set-tier", help="Set user tier")
    set_tier_parser.add_argument("email", help="User email")
    set_tier_parser.add_argument("tier", choices=["free", "paid", "unlimited"], help="Tier to set")

    # list-users command
    subparsers.add_parser("list-users", help="List all users")

    # user-info command
    user_info_parser = subparsers.add_parser("user-info", help="Show user info")
    user_info_parser.add_argument("email", help="User email")

    args = parser.parse_args()

    if args.command == "set-tier":
        set_tier(args.email, args.tier)
    elif args.command == "list-users":
        list_users()
    elif args.command == "user-info":
        user_info(args.email)


if __name__ == "__main__":
    main()
