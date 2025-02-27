import os
import json
import requests

# Environment variables from GitHub Action
pr_number = os.getenv("PR_NUMBER")
pr_user = os.getenv("PR_USER")
slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
github_token = os.getenv("GITHUB_TOKEN")
repository = os.getenv("REPOSITORY")

# Handle missing repository variable
if not repository:
    # Fallback - try to get from GitHub environment file
    try:
        with open(os.getenv("GITHUB_ENV", ""), "r") as f:
            for line in f:
                if line.startswith("GITHUB_REPOSITORY="):
                    repository = line.strip().split("=", 1)[1]
                    break
    except FileNotFoundError:
        print("GitHub environment file not found.")
        exit(1)
    except Exception as e:
        print(f"An error occurred while reading the environment file: {e}")
        exit(1)

    # If still not found, exit with error
    if not repository:
        print("Error: Repository name not available in environment variables.")
        exit(1)

# Load Slack mapping from file
mapping_file = ".github/slack-mapping.json"
try:
    with open(mapping_file, "r") as file:
        slack_mapping = json.load(file)
except FileNotFoundError:
    print("Slack mapping file not found.")
    exit(1)
except json.JSONDecodeError:
    print("Invalid JSON format in slack-mapping.json.")
    exit(1)

# GitHub API URLs
pr_api_url = f"https://api.github.com/repos/{repository}/pulls/{pr_number}"
user_api_url = f"https://api.github.com/users/{pr_user}"

# Debugging URL
print(f"Fetching PR details from: {pr_api_url}")

# Get PR details with authentication
headers = {
    "Authorization": f"token {github_token}",
    "Accept": "application/vnd.github.v3+json",
}

# Fetch PR details
pr_response = requests.get(pr_api_url, headers=headers)
if pr_response.status_code != 200:
    print(f"Failed to fetch PR details. Status Code: {pr_response.status_code}")
    print(f"Response: {pr_response.text}")
    exit(1)

pr_data = pr_response.json()
labels = [label["name"] for label in pr_data.get("labels", [])]
pr_title = pr_data.get("title", "Pull Request")
pr_url = pr_data.get("html_url", f"https://github.com/{repository}/pull/{pr_number}")

# Fetch GitHub user details
user_response = requests.get(user_api_url, headers=headers)
if user_response.status_code != 200:
    print(f"Failed to fetch user details. Status Code: {user_response.status_code}")
    print(f"Response: {user_response.text}")
    exit(1)

user_data = user_response.json()
profile_picture = user_data.get(
    "avatar_url",
    "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
)

# Check if 'database' label is present
if "database" in labels:
    # Get Slack user ID from mapping
    slack_user_id = slack_mapping["mappings"].get(pr_user, None)
    if slack_user_id:
        # Mention the Slack user with direct ping
        mention = f"<@{slack_user_id}>"
    else:
        # If no mapping is found, just use the GitHub username
        mention = f"@{pr_user}"

    # Prepare Slack message with links and mention
    slack_message = {
        "text": (
            f"{mention}, your PR *<{pr_url}|{pr_title}>* has the *'database'* label! "
            "Don't forget to release fields in metadata."
        ),
        "username": pr_user,
        "icon_url": profile_picture,
    }

    # Send message to Slack
    slack_response = requests.post(slack_webhook_url, json=slack_message)
    if slack_response.status_code != 200:
        print(f"Failed to send message to Slack: {slack_response.text}")
        exit(1)
    else:
        print("Notification sent to Slack.")
else:
    print("No 'database' label found. No notification sent.")
