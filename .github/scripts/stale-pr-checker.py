import os
import requests
import json
from datetime import datetime, timezone

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("REPO")
STALE_DAYS = int(os.getenv("STALE_DAYS", 3))
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
pr_url = f"https://api.github.com/repos/{REPO}/pulls?state=open"

response = requests.get(pr_url, headers=headers)
if response.status_code != 200:
    print(f"Error fetching PRs: {response.json().get('message')}")
    exit(1)

stale_prs = []
now = datetime.now(timezone.utc)

for pr in response.json():
    pr_id = pr["number"]
    creator = pr["user"]["login"]
    pr_link = pr["html_url"]
    created_at = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
    age = (now - created_at).days

    if age >= STALE_DAYS:
        labels_url = f"https://api.github.com/repos/{REPO}/issues/{pr_id}/labels"
        labels_response = requests.get(labels_url, headers=headers)

        if any(label["name"] == "Notified" for label in labels_response.json()):
            print(f"PR #{pr_id} already notified, skipping.")
            continue

        # Comment on PR
        comment_url = f"https://api.github.com/repos/{REPO}/issues/{pr_id}/comments"
        comment = {
            "body": f"@{creator} This PR has been open for {age} days. Please update its status."
        }
        requests.post(comment_url, headers=headers, json=comment)

        # Add "Notified" label
        requests.post(labels_url, headers=headers, json={"labels": ["Notified"]})

        stale_prs.append({"id": pr_id, "creator": creator, "url": pr_link, "age": age})

if stale_prs and SLACK_WEBHOOK_URL:
    for pr in stale_prs:
        slack_payload = {
            "text": f"🚨 Stale PR Detected: <{pr['url']}|#{pr['id']}> by @{pr['creator']}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*🚨 Stale PR Detected*\n*PR:* <{pr['url']}|#{pr['id']}>\n*Creator:* @{pr['creator']}\n*Age:* {pr['age']} days",
                    },
                }
            ],
        }
        requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
        print(f"Slack notification sent for PR #{pr['id']}")
else:
    print("No stale PRs found.")
