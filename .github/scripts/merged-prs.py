import requests
import os
import sys
from datetime import datetime, timedelta


def fetch_and_log_prs(start_date, end_date):
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("REPO")
    headers = {"Authorization": f"token {token}"}

    # Handle the start_date and end_date inputs
    if start_date == "yesterday":
        since = datetime.utcnow() - timedelta(days=1)
    else:
        try:
            since = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            print(
                f"Invalid start date format: {start_date}. Expected format is YYYY-MM-DD."
            )
            return

    if end_date == "today":
        until = datetime.utcnow()
    else:
        try:
            until = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            print(
                f"Invalid end date format: {end_date}. Expected format is YYYY-MM-DD."
            )
            return

    response = requests.get(
        f"https://api.github.com/repos/{repo}/pulls?state=closed", headers=headers
    )
    prs = response.json()

    merged_prs = [
        pr
        for pr in prs
        if pr.get("merged_at")
        and since <= datetime.strptime(pr["merged_at"], "%Y-%m-%dT%H:%M:%SZ") <= until
    ]

    with open("merged_prs.log", "w") as log_file:
        if merged_prs:
            log_file.write(
                f"Merged PRs between {since.strftime('%Y-%m-%d')} and {until.strftime('%Y-%m-%d')}:\n"
            )
            for pr in merged_prs:
                merged_at = datetime.strptime(pr["merged_at"], "%Y-%m-%dT%H:%M:%SZ")
                merged_at_str = merged_at.strftime("%Y-%m-%d | %H:%M")
                log_file.write(f"- {pr['title']} (Merged at: {merged_at_str})\n")
        else:
            log_file.write(
                f"No PRs merged between {since.strftime('%Y-%m-%d')} and {until.strftime('%Y-%m-%d')}."
            )


if __name__ == "__main__":
    # Use the first and second arguments passed to the script as the start and end dates
    start_date = sys.argv[1] if len(sys.argv) > 1 else "yesterday"
    end_date = sys.argv[2] if len(sys.argv) > 2 else "today"
    fetch_and_log_prs(start_date, end_date)
