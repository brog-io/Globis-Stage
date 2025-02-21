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
        self.stale_days = int(os.getenv("STALE_DAYS", "3"))
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

    def should_check_pr(self) -> bool:
        """Determine if we should check PRs based on the trigger event."""
        if self.event_name == "schedule":
            return True
        elif self.event_name == "workflow_dispatch":
            return True
        elif self.event_name == "pull_request":
            # Only check the specific PR that triggered the workflow
            try:
                with open(self.event_path) as f:
                    event_data = json.load(f)
                    pr_number = event_data["pull_request"]["number"]
                    self.logger.info(f"Pull request event for PR #{pr_number}")
                    return True
            except Exception as e:
                self.logger.error(f"Error reading event data: {e}")
                return False
        return False

    def get_pull_requests(self) -> List[Dict]:
        """Fetch pull requests based on the event type."""
        if self.event_name == "pull_request":
            # For PR events, only check the triggering PR
            with open(self.event_path) as f:
                event_data = json.load(f)
                pr_number = event_data["pull_request"]["number"]
                pr_url = f"https://api.github.com/repos/{self.repo}/pulls/{pr_number}"
                response = requests.get(pr_url, headers=self.headers)
                response.raise_for_status()
                return [response.json()]
        else:
            # For scheduled runs, check all open PRs
            pr_url = f"https://api.github.com/repos/{self.repo}/pulls?state=open"
            response = requests.get(pr_url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    def is_pr_notified(self, pr_id: int) -> bool:
        """Check if PR has already been notified."""
        labels_url = f"https://api.github.com/repos/{self.repo}/issues/{pr_id}/labels"
        response = requests.get(labels_url, headers=self.headers)
        response.raise_for_status()
        return any(label["name"] == "Notified" for label in response.json())

    def notify_pr(self, pr: PullRequest) -> None:
        """Add comment and label to PR."""
        # Add comment
        comment_url = (
            f"https://api.github.com/repos/{self.repo}/issues/{pr.id}/comments"
        )
        comment = {
            "body": f"@{pr.creator} This PR has been open for {pr.age} days. Please update its status."
        }
        response = requests.post(comment_url, headers=self.headers, json=comment)
        response.raise_for_status()

        # Add label
        labels_url = f"https://api.github.com/repos/{self.repo}/issues/{pr.id}/labels"
        response = requests.post(
            labels_url, headers=self.headers, json={"labels": ["Notified"]}
        )
        response.raise_for_status()

        self.logger.info(f"Notified PR #{pr.id}")

    def send_slack_notification(self, pr: PullRequest) -> None:
        """Send notification to Slack."""
        if not self.slack_webhook_url:
            return

        slack_payload = {
            "text": f"🚨 Stale PR Detected: <{pr.url}|#{pr.id}> by @{pr.creator}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*🚨 Stale PR Detected*\n*PR:* <{pr.url}|#{pr.id}>\n*Creator:* @{pr.creator}\n*Age:* {pr.age} days",
                    },
                }
            ],
        }

        response = requests.post(self.slack_webhook_url, json=slack_payload)
        response.raise_for_status()
        self.logger.info(f"Slack notification sent for PR #{pr.id}")

    def process_pull_requests(self) -> None:
        """Main method to process all pull requests."""
        if not self.should_check_pr():
            self.logger.info("Skipping PR check based on trigger event")
            return

        try:
            self.logger.info(f"Starting PR check for {self.repo}")
            self.logger.info(f"Event type: {self.event_name}")

            pull_requests = self.get_pull_requests()
            now = datetime.now(timezone.utc)
            stale_prs = []

            for pr_data in pull_requests:
                pr_id = pr_data["number"]
                created_at = datetime.fromisoformat(
                    pr_data["created_at"].replace("Z", "+00:00")
                )
                age = (now - created_at).days

                if age >= self.stale_days and not self.is_pr_notified(pr_id):
                    pr = PullRequest(
                        id=pr_id,
                        creator=pr_data["user"]["login"],
                        url=pr_data["html_url"],
                        created_at=created_at,
                        age=age,
                    )

                    try:
                        self.notify_pr(pr)
                        self.send_slack_notification(pr)
                        stale_prs.append(pr)
                    except requests.RequestException as e:
                        self.logger.error(f"Error processing PR #{pr_id}: {str(e)}")

            if not stale_prs:
                self.logger.info("No stale PRs found")
            else:
                self.logger.info(f"Processed {len(stale_prs)} stale PRs")

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
