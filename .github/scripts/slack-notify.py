import os
import json
import time
import requests
from github import Github

# Load environment variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
REPO = os.getenv("GITHUB_REPOSITORY")
USE_CODEOWNERS = os.getenv("USE_CODEOWNERS", "false").lower() == "true"

github = Github(GITHUB_TOKEN)
repo = github.get_repo(REPO)


def load_required_workflows():
    """Load required workflows from a JSON file."""
    workflow_path = ".github/workflows.json"

    if not os.path.exists(workflow_path):
        print("Warning: workflows.json not found.")
        return []

    try:
        with open(workflow_path, "r") as f:
            data = json.load(f)
            workflows = data.get("required_workflows", [])
            print(f"Loaded Required Workflows: {workflows}")
            return workflows
    except json.JSONDecodeError:
        print("Error: Invalid JSON in workflows.json")
    except Exception as e:
        print(f"Error loading workflows.json: {str(e)}")
    return []


# Load required workflows
REQUIRED_WORKFLOWS = load_required_workflows()


def get_event_data():
    """Read GitHub event data from the provided event path."""
    event_path = os.getenv("GITHUB_EVENT_PATH")
    with open(event_path, "r") as f:
        return json.load(f)


def load_slack_user_map():
    """Load GitHub-to-Slack username mappings from JSON file."""
    mapping_path = ".github/slack-mapping.json"

    if not os.path.exists(mapping_path):
        print("Warning: slack-mapping.json not found.")
        return {}

    try:
        with open(mapping_path, "r") as f:
            data = json.load(f)
            mappings = data.get("mappings", {})
            print(f"Loaded Slack Mapping: {mappings}")
            return mappings
    except json.JSONDecodeError:
        print("Error: Invalid JSON in slack-mapping.json")
    except Exception as e:
        print(f"Error loading slack-mapping.json: {str(e)}")
    return {}


def get_codeowners():
    """Retrieve CODEOWNERS file and extract user mentions."""
    try:
        codeowners_file = repo.get_contents("CODEOWNERS").decoded_content.decode()
        codeowners = {}
        for line in codeowners_file.splitlines():
            # Ignore blank lines and comments
            if line.strip() and not line.startswith("#"):
                parts = line.strip().split()
                if len(parts) > 1:
                    owners = [user.replace("@", "") for user in parts[1:]]
                    codeowners[parts[0]] = owners
        return codeowners
    except Exception as e:
        print(f"Warning: Error loading CODEOWNERS: {str(e)}")
        return {}


def get_changed_files(pr_number):
    """Fetch changed files for a pull request."""
    pr = repo.get_pull(pr_number)
    files = pr.get_files()
    return [file.filename for file in files]


def check_actions_finished(pr_data):
    """
    Verifies that specific GitHub actions have finished.
    Returns True only if all required workflows have completed successfully.
    """
    try:
        workflow_token = os.getenv("GITHUB_TOKEN")
        pr_number = pr_data["pull_request"]["number"]
        head_sha = pr_data["pull_request"]["head"]["sha"]
        repo_full_name = pr_data["repository"]["full_name"]

        headers = {
            "Authorization": f"token {workflow_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        api_base = "https://api.github.com"
        retries = 0
        max_retries = 120

        while retries < max_retries:
            retries += 1
            checks_url = (
                f"{api_base}/repos/{repo_full_name}/commits/{head_sha}/check-runs"
            )
            checks_response = requests.get(checks_url, headers=headers)

            if checks_response.status_code != 200:
                print(f"Error fetching check runs: {checks_response.status_code}")
                time.sleep(30)
                continue

            check_runs = checks_response.json().get("check_runs", [])
            workflows = {workflow: False for workflow in REQUIRED_WORKFLOWS}

            for check in check_runs:
                name = check.get("name", "")
                status = check.get("status", "")
                conclusion = check.get("conclusion", "")

                if (
                    name in REQUIRED_WORKFLOWS
                    and status == "completed"
                    and conclusion == "success"
                ):
                    workflows[name] = True

            if all(workflows.values()):
                print("All required workflows have completed successfully!")
                return True

            print("Not all actions have completed, waiting for 30 seconds...")
            time.sleep(30)

        print("Max retries reached, aborting.")
        return False

    except Exception as e:
        print(f"Error checking actions status: {str(e)}")
        return False


def format_pr_created_message(pr_data, codeowners, slack_user_map):
    """Format Slack notification message for PR creation."""
    pr_number = pr_data["pull_request"]["number"]
    pr_title = pr_data["pull_request"]["title"]
    pr_url = pr_data["pull_request"]["html_url"]

    notify_users = set()
    notify_users.update(
        user["login"] for user in pr_data["pull_request"].get("assignees", [])
    )
    notify_users.update(
        r["login"] for r in pr_data["pull_request"].get("requested_reviewers", [])
    )

    if USE_CODEOWNERS:
        changed_files = get_changed_files(pr_number)
        for path, owners in codeowners.items():
            if any(file.startswith(path) for file in changed_files):
                notify_users.update(owners)

    slack_mentions, unmapped_users = convert_to_slack_mentions(
        notify_users, slack_user_map
    )

    # Format the message as a single line
    notification_line = f"*<{pr_url}|PR #{pr_number}: {pr_title}>*"
    if slack_mentions:
        notification_line += f" - Notifying: {' '.join(slack_mentions)}"

    message = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": notification_line,
                },
            }
        ]
    }

    return message


def convert_to_slack_mentions(github_users, slack_user_map):
    """Convert GitHub usernames to Slack mentions."""
    slack_mentions = []
    unmapped_users = []

    for github_user in github_users:
        slack_id = slack_user_map.get(github_user)
        if slack_id:
            slack_mentions.append(f"<@{slack_id}>")
        else:
            unmapped_users.append(github_user)

    return slack_mentions, unmapped_users


def get_github_avatar_url(username):
    """Fetch GitHub avatar URL for a given username."""
    try:
        user = github.get_user(username)
        return user.avatar_url
    except Exception as e:
        print(f"Error fetching avatar for {username}: {str(e)}")
        return None


def send_slack_notification(message, username):
    """Send Slack notification using webhook with custom username and avatar."""
    try:
        avatar_url = get_github_avatar_url(username)
        message["username"] = username

        if avatar_url:
            message["icon_url"] = avatar_url

        headers = {"Content-Type": "application/json"}
        response = requests.post(SLACK_WEBHOOK_URL, json=message, headers=headers)
        response.raise_for_status()
        print("Successfully sent Slack notification")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send Slack notification: {str(e)}")


if __name__ == "__main__":
    event_data = get_event_data()
    slack_user_map = load_slack_user_map()
    pr_creator = event_data["pull_request"]["user"]["login"]
    codeowners = get_codeowners() if USE_CODEOWNERS else {}

    if check_actions_finished(event_data):
        slack_message = format_pr_created_message(
            event_data, codeowners, slack_user_map
        )
        send_slack_notification(slack_message, pr_creator)
    else:
        print("Required actions not completed. Aborting notification.")
        exit(1)
