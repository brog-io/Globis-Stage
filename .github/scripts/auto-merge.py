# Import necessary libraries
import os  # For accessing environment variables
import requests  # For making HTTP requests to GitHub API


def get_github_api_headers():
    """
    Create and return headers required for GitHub API authentication.

    Returns:
        dict: Headers including the authentication token and API version specification
    """
    return {
        "Authorization": f"Bearer {os.getenv('GH_TOKEN')}",  # Use GitHub token from environment variable
        "Accept": "application/vnd.github.v3+json",  # Specify GitHub API version
    }


def get_pr_details(repo, pr_number):
    """
    Fetch detailed information about a specific pull request.

    Args:
        repo (str): Repository name in format 'owner/repo'
        pr_number (str): Pull request number

    Returns:
        dict: JSON response containing PR details

    Raises:
        HTTPError: If the API request fails
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    response = requests.get(url, headers=get_github_api_headers())
    response.raise_for_status()  # Raise exception for 4XX/5XX responses
    return response.json()


def get_pr_labels(repo, pr_number):
    """
    Fetch labels attached to a specific pull request.

    Args:
        repo (str): Repository name in format 'owner/repo'
        pr_number (str): Pull request number

    Returns:
        list: List of label names

    Raises:
        HTTPError: If the API request fails
    """
    # Note: GitHub's API uses the issues endpoint for PR labels
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/labels"
    response = requests.get(url, headers=get_github_api_headers())
    response.raise_for_status()
    return [label["name"] for label in response.json()]  # Extract just the label names


def is_pr_approved(repo, pr_number):
    """
    Check if a pull request has been approved by reviewers.

    Args:
        repo (str): Repository name in format 'owner/repo'
        pr_number (str): Pull request number

    Returns:
        bool: True if PR has at least one approval, False otherwise

    Raises:
        HTTPError: If the API request fails
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    response = requests.get(url, headers=get_github_api_headers())
    response.raise_for_status()
    # Return True if any review has an 'APPROVED' state
    return any(review["state"] == "APPROVED" for review in response.json())


def enable_auto_merge(repo, pr_number):
    """
    Immediately merge a pull request.

    Args:
        repo (str): Repository name in format 'owner/repo'
        pr_number (str): Pull request number

    Raises:
        HTTPError: If the API request fails or the merge cannot be completed
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/merge"
    response = requests.put(
        url, headers=get_github_api_headers(), json={"merge_method": "merge"}
    )
    response.raise_for_status()
    print("Auto-merged PR successfully.")


def main():
    """
    Main function to process a PR for potential auto-merging.

    The function will:
    1. Check that required environment variables are set
    2. Skip if the PR has the 'no-auto-merge' label
    3. Skip if the PR isn't approved
    4. Auto-merge the PR if conditions are met
    """
    # Get repository and PR number from environment variables
    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")

    # Validate required inputs
    if not repo or not pr_number:
        print("Missing repository or PR number.")
        return

    # Check for label that would prevent auto-merge
    if "no-auto-merge" in get_pr_labels(repo, pr_number):
        print("PR has 'no-auto-merge' label, skipping auto-merge.")
        return

    # Check if PR is approved
    if not is_pr_approved(repo, pr_number):
        print("PR is not approved, skipping auto-merge.")
        return

    # If we got here, auto-merge the PR
    enable_auto_merge(repo, pr_number)


if __name__ == "__main__":
    main()
