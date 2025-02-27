# Import necessary libraries
import requests  # For making HTTP requests to GitHub API
import os  # For accessing environment variables
import sys  # For accessing command line arguments
from datetime import datetime, timedelta  # For date handling


def fetch_and_log_prs(start_date, end_date):
    """
    Fetch merged pull requests for a GitHub repository within a date range and log them to a file.

    Args:
        start_date (str): Starting date in YYYY-MM-DD format or "yesterday"
        end_date (str): Ending date in YYYY-MM-DD format or "today"
    """
    # Get GitHub authentication token and repository from environment variables
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("REPO")
    headers = {"Authorization": f"token {token}"}  # Set up authentication headers

    # Handle the start_date input
    if start_date == "yesterday":
        # Convert "yesterday" to an actual date (24 hours ago)
        since = datetime.utcnow() - timedelta(days=1)
    else:
        try:
            # Convert string date to datetime object
            since = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            # Handle invalid date format
            print(
                f"Invalid start date format: {start_date}. Expected format is YYYY-MM-DD."
            )
            return

    # Handle the end_date input
    if end_date == "today":
        # Use current time for "today"
        until = datetime.utcnow()
    else:
        try:
            # Convert string date to datetime object
            until = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            # Handle invalid date format
            print(
                f"Invalid end date format: {end_date}. Expected format is YYYY-MM-DD."
            )
            return

    # Make API request to fetch closed PRs from the repository
    response = requests.get(
        f"https://api.github.com/repos/{repo}/pulls?state=closed", headers=headers
    )
    prs = response.json()

    # Filter PRs that were merged within the specified date range
    merged_prs = [
        pr
        for pr in prs
        if pr.get("merged_at")  # Only consider PRs that were actually merged
        and since
        <= datetime.strptime(pr["merged_at"], "%Y-%m-%dT%H:%M:%SZ")
        <= until  # Check if PR was merged within date range
    ]

    # Write the results to a log file
    with open("merged_prs.log", "w") as log_file:
        if merged_prs:
            # Write header with date range
            log_file.write(
                f"Merged PRs between {since.strftime('%Y-%m-%d')} and {until.strftime('%Y-%m-%d')}:\n"
            )
            # Write details for each merged PR
            for pr in merged_prs:
                # Format the merge timestamp
                merged_at = datetime.strptime(pr["merged_at"], "%Y-%m-%dT%H:%M:%SZ")
                merged_at_str = merged_at.strftime("%Y-%m-%d | %H:%M")
                # Log PR title and merge time
                log_file.write(f"- {pr['title']} (Merged at: {merged_at_str})\n")
        else:
            # No PRs found in the date range
            log_file.write(
                f"No PRs merged between {since.strftime('%Y-%m-%d')} and {until.strftime('%Y-%m-%d')}."
            )


if __name__ == "__main__":
    # Script is being run directly (not imported)
    # Use the first and second arguments passed to the script as the start and end dates
    start_date = (
        sys.argv[1] if len(sys.argv) > 1 else "yesterday"
    )  # Default to "yesterday" if not provided
    end_date = (
        sys.argv[2] if len(sys.argv) > 2 else "today"
    )  # Default to "today" if not provided
    fetch_and_log_prs(start_date, end_date)
