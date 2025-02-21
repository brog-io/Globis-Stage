import os
import requests


def get_github_api_headers():
    return {
        "Authorization": f"Bearer {os.getenv('GH_TOKEN')}",
        "Accept": "application/vnd.github.v3+json",
    }


def get_pr_details(repo, pr_number):
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    response = requests.get(url, headers=get_github_api_headers())
    response.raise_for_status()
    return response.json()


def get_pr_labels(repo, pr_number):
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/labels"
    response = requests.get(url, headers=get_github_api_headers())
    response.raise_for_status()
    return [label["name"] for label in response.json()]


def is_pr_approved(repo, pr_number):
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    response = requests.get(url, headers=get_github_api_headers())
    response.raise_for_status()
    return any(review["state"] == "APPROVED" for review in response.json())


def enable_auto_merge(repo, pr_number):
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/merge"
    response = requests.put(
        url, headers=get_github_api_headers(), json={"merge_method": "merge"}
    )
    response.raise_for_status()
    print("Auto-merged PR successfully.")


def main():
    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")

    if not repo or not pr_number:
        print("Missing repository or PR number.")
        return

    if "no-auto-merge" in get_pr_labels(repo, pr_number):
        print("PR has 'no-auto-merge' label, skipping auto-merge.")
        return

    if not is_pr_approved(repo, pr_number):
        print("PR is not approved, skipping auto-merge.")
        return

    enable_auto_merge(repo, pr_number)


if __name__ == "__main__":
    main()
