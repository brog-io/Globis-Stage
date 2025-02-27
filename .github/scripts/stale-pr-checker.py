import os
import sys
import json
import requests
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class PullRequest:
    id: int
    creator: str
    url: str
    created_at: datetime
    age: int
    labels: List[str]


def load_slack_mappings() -> Dict[str, str]:
    """Load Slack user mappings from .github/slack-mapping.json."""
    try:
        with open(".github/slack-mapping.json", "r") as f:
            data = json.load(f)
            return data.get("mappings", {})
    except Exception as e:
        logging.error(f"Failed to load Slack mappings: {str(e)}")
        return {}


class GitHubPRMonitor:
    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.repo = os.getenv("REPO")
        self.stale_days = int(os.getenv("STALE_DAYS", "3"))
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")

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

        # Load Slack mappings
        self.slack_mappings = load_slack_mappings()

    def get_pull_requests(self) -> List[Dict]:
        """Fetch all open pull requests."""
        pr_url = f"https://api.github.com/repos/{self.repo}/pulls?state=open"
        self.logger.info(f"Fetching PRs from: {pr_url}")
        response = requests.get(pr_url, headers=self.headers)
        response.raise_for_status()
        prs = response.json()
        self.logger.info(f"Found {len(prs)} open PRs")
        return prs

    def determine_stale_reason(self, pr: PullRequest) -> str:
        """Determine the reason why a PR is considered stale."""
        reason = "This PR has been open for too long and requires attention."

        # Check for failing workflows
        check_runs_url = (
            f"https://api.github.com/repos/{self.repo}/pulls/{pr.id}/check-runs"
        )
        response = requests.get(check_runs_url, headers=self.headers)
        if response.status_code == 200:
            check_runs_data = response.json()
            failed_checks = [
                run
                for run in check_runs_data.get("check_runs", [])
                if run["conclusion"] == "failure"
            ]
            if failed_checks:
                return "Workflows failed for this PR."

        # Check for pending reviews
        reviews_url = f"https://api.github.com/repos/{self.repo}/pulls/{pr.id}/reviews"
        response = requests.get(reviews_url, headers=self.headers)
        if response.status_code == 200:
            review_data = response.json()
            pending_reviews = any(
                review["state"] in ["PENDING", "CHANGES_REQUESTED"]
                for review in review_data
            )
            if pending_reviews:
                return "A review is required or changes were requested."

        return reason

    def notify_pr(self, pr: PullRequest) -> None:
        """Add comment and label to PR."""
        comment_url = (
            f"https://api.github.com/repos/{self.repo}/issues/{pr.id}/comments"
        )
        comment = {
            "body": f"@{pr.creator} This PR has been open for {pr.age} days, please provide an update on its status."
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

        slack_user_id = self.slack_mappings.get(pr.creator, None)
        mention = f"<@{slack_user_id}>" if slack_user_id else f"@{pr.creator}"
        reason = self.determine_stale_reason(pr)

        slack_payload = {
            "text": f"🚨 Stale PR <{pr.url}|#{pr.id}> Alert",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*🚨 Stale PR <{pr.url}|#{pr.id}> Alert*\n"
                            f"*Creator:* {mention}\n"
                            f"*Age:* {pr.age} days\n"
                            f"*Status:* {reason}"
                        ),
                    },
                }
            ],
        }

        response = requests.post(self.slack_webhook_url, json=slack_payload)
        response.raise_for_status()
        self.logger.info(f"Slack notification sent for PR #{pr.id}")

    def process_pull_requests(self) -> None:
        """Process PRs that are older than the stale threshold and do not have the 'stale' label."""
        try:
            self.logger.info(f"Starting stale PR check for {self.repo}")
            self.logger.info(f"Stale threshold: {self.stale_days} days")

            pull_requests = self.get_pull_requests()
            now = datetime.now(timezone.utc)

            for pr_data in pull_requests:
                pr_id = pr_data["number"]
                created_at = datetime.fromisoformat(
                    pr_data["created_at"].replace("Z", "+00:00")
                )
                age = (now - created_at).days
                labels = [label["name"] for label in pr_data.get("labels", [])]

                if "stale" in labels or age < self.stale_days:
                    continue

                pr = PullRequest(
                    id=pr_id,
                    creator=pr_data["user"]["login"],
                    url=pr_data["html_url"],
                    created_at=created_at,
                    age=age,
                    labels=labels,
                )

                self.notify_pr(pr)
                self.send_slack_notification(pr)

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
