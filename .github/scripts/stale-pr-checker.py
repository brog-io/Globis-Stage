import os
import sys
import requests
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging


@dataclass
class PullRequest:
    id: int
    creator: str
    url: str
    created_at: datetime
    age: int


class GitHubPRMonitor:
    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.repo = os.getenv("REPO")
        self.stale_days = int(os.getenv("STALE_DAYS", "1"))
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.event_name = os.getenv("GITHUB_EVENT_NAME", "")
        self.event_path = os.getenv("GITHUB_EVENT_PATH", "")

        if not all([self.github_token, self.repo]):
            raise ValueError(
                "Missing required environment variables: GITHUB_TOKEN, REPO"
            )

        self.headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger(__name__)

    def get_pull_requests(self) -> List[Dict]:
        """Fetch all open pull requests."""
        pr_url = f"https://api.github.com/repos/{self.repo}/pulls?state=open"
        self.logger.info(f"Fetching PRs from: {pr_url}")
        response = requests.get(pr_url, headers=self.headers)
        response.raise_for_status()
        prs = response.json()
        self.logger.info(f"Found {len(prs)} open PRs")
        return prs

    def notify_pr(self, pr: PullRequest) -> None:
        """Add comment and label to PR."""
        # Add comment
        comment_url = (
            f"https://api.github.com/repos/{self.repo}/issues/{pr.id}/comments"
        )
        comment = {
            "body": f"@{pr.creator} This PR has been open for more than {self.stale_days} days. Please update or close it."
        }
        response = requests.post(comment_url, headers=self.headers, json=comment)
        response.raise_for_status()

        # Add label
        labels_url = f"https://api.github.com/repos/{self.repo}/issues/{pr.id}/labels"
        response = requests.post(
            labels_url, headers=self.headers, json={"labels": ["stale"]}
        )
        response.raise_for_status()

        self.logger.info(f"Notified PR #{pr.id}")

    def send_slack_notification(self, pr: PullRequest) -> None:
        """Send notification to Slack."""
        if not self.slack_webhook_url:
            self.logger.info(
                "No Slack webhook URL configured, skipping Slack notification"
            )
            return

        slack_payload = {
            "text": f"🚨 Stale PR Alert: <{pr.url}|#{pr.id}> by @{pr.creator}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*🚨 Stale PR Alert*\n*PR:* <{pr.url}|#{pr.id}>\n*Creator:* @{pr.creator}\n*Age:* {pr.age} days\n*Status:* Needs attention",
                    },
                }
            ],
        }

        response = requests.post(self.slack_webhook_url, json=slack_payload)
        response.raise_for_status()
        self.logger.info(f"Slack notification sent for PR #{pr.id}")

    def process_pull_requests(self) -> None:
        """Process PRs that are older than the stale threshold."""
        try:
            self.logger.info(f"Starting stale PR check for {self.repo}")
            self.logger.info(f"Event type: {self.event_name}")
            self.logger.info(f"Stale threshold: {self.stale_days} days")

            pull_requests = self.get_pull_requests()
            now = datetime.now(timezone.utc)
            processed_prs = []

            for pr_data in pull_requests:
                pr_id = pr_data["number"]
                created_at = datetime.fromisoformat(
                    pr_data["created_at"].replace("Z", "+00:00")
                )
                age = (now - created_at).days

                # Skip PRs that aren't old enough
                if age >= self.stale_days:
                    self.logger.info(f"Skipping PR #{pr_id} (age: {age} days)")
                    continue

                # Create PR object for stale PRs
                pr = PullRequest(
                    id=pr_id,
                    creator=pr_data["user"]["login"],
                    url=pr_data["html_url"],
                    created_at=created_at,
                    age=age,
                )

                self.logger.info(f"Processing stale PR #{pr_id} (age: {age} days)")

                try:
                    self.notify_pr(pr)
                    self.send_slack_notification(pr)
                    processed_prs.append(pr)
                except requests.RequestException as e:
                    self.logger.error(f"Error processing PR #{pr_id}: {str(e)}")

            if not processed_prs:
                self.logger.info("No stale PRs found")
            else:
                self.logger.info(
                    f"Successfully processed {len(processed_prs)} stale PRs"
                )

        except requests.RequestException as e:
            self.logger.error(f"Error fetching PRs: {str(e)}")
            sys.exit(1)


def main():
    try:
        monitor = GitHubPRMonitor()
        monitor.process_pull_requests()
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
