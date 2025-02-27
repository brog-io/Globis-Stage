import os
import re
import requests
import yaml
import fnmatch
from github import Github

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = os.getenv("GITHUB_REPOSITORY")
PR_NUMBER = os.getenv("GITHUB_EVENT_PULL_REQUEST_NUMBER")
CODEOWNERS_PATH = "CODEOWNERS"  # Path to the CODEOWNERS file (default: repository root)
FILTER_YML_PATH = ".github/filters.yml"  # Path to the filters YAML file
DEFAULT_LABEL_COLOR = "CCCCCC"


class GitHubLabelError(Exception):
    """Custom exception for GitHub labeling errors"""

    pass


def validate_environment():
    """Validate required environment variables are set."""
    required_vars = {
        "GITHUB_TOKEN": GITHUB_TOKEN,
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_EVENT_PULL_REQUEST_NUMBER": PR_NUMBER,
    }
    missing_vars = [var for var, value in required_vars.items() if not value]
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )


def get_changed_files(github_client, repo_name, pr_number):
    """Fetch the changed files in the pull request using PyGithub."""
    try:
        repo = github_client.get_repo(repo_name)
        pull_request = repo.get_pull(pr_number)
        return [file.filename for file in pull_request.get_files()]
    except Exception as e:
        raise GitHubLabelError(f"Failed to fetch changed files: {str(e)}")


def read_codeowners(repo, branch=None):
    """
    Read the CODEOWNERS file and extract valid label paths and user assignments.
    If a branch is provided, the file is fetched from that branch.
    """
    try:
        if branch:
            contents = repo.get_contents(CODEOWNERS_PATH, ref=branch)
        else:
            contents = repo.get_contents(CODEOWNERS_PATH)
        codeowners_data = contents.decoded_content.decode("utf-8")
    except Exception as e:
        print(f"Warning: Failed to read CODEOWNERS file: {e}")
        return set(), {}

    valid_labels = set()
    assignees_map = {}

    for line in codeowners_data.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Extract the path and the list of assignees (usernames starting with @)
        match = re.match(r"(\S+)\s+(@[\w-]+(?:\s+@[\w-]+)*)", line)
        if match:
            path = match.group(1).rstrip("/")
            if path.startswith("/"):
                path = path[1:]
            valid_labels.add(path)
            assignees = match.group(2).split()
            assignees_map[path] = assignees

    print(f"Extracted CODEOWNERS paths: {valid_labels}")
    return valid_labels, assignees_map


def read_filter_yml():
    """Read the filter.yml file and parse it into a dictionary."""
    try:
        with open(FILTER_YML_PATH, "r") as file:
            filter_data = yaml.safe_load(file)
        return filter_data
    except Exception as e:
        print(f"Warning: Failed to read filter.yml file: {e}")
        return {}


def get_label_for_file(file, filter_data):
    """Get label for the file based on filter.yml mapping."""
    for label, patterns in filter_data.items():
        if isinstance(patterns, list):
            for pattern in patterns:
                if fnmatch.fnmatch(file, pattern):
                    return label
        elif fnmatch.fnmatch(file, patterns):
            return label
    return None


def process_files(changed_files, valid_labels, filter_data):
    """
    Generate labels based on changed files.
    Priority is given to any label found in filters.yml. If none is found,
    then the CODEOWNERS file is used to match a directory or file path.
    """
    labels = set()

    for file in changed_files:
        print(f"\nProcessing file: {file}")

        # First check the filters.yml mappings (highest priority)
        special_label = get_label_for_file(file, filter_data)
        if special_label:
            labels = {special_label}
            print(f"Matched {file} to filters.yml label: {special_label}")
            return labels

        # Otherwise, check the CODEOWNERS mapping.
        parts = file.split("/")
        for i in range(len(parts), 0, -1):
            possible_label = "/".join(parts[:i])
            if possible_label in valid_labels:
                labels.add(possible_label)
                print(f"Matched {file} to CODEOWNERS label: {possible_label}")
                break

    return labels


def create_labels(repo, labels):
    """Create labels in the repository if they don't already exist."""
    existing_labels = {label.name: label for label in repo.get_labels()}

    for label in labels:
        if label not in existing_labels:
            try:
                repo.create_label(
                    name=label,
                    color=DEFAULT_LABEL_COLOR,
                    description="Auto-generated from directory structure",
                )
                print(f"Created label: {label}")
            except Exception as e:
                print(f"Warning: Failed to create label '{label}': {e}")


def get_assignees_for_path(file_path, assignees_map):
    """
    Determine the set of assignees for a given file path based on the CODEOWNERS mapping.
    Checks for an exact match, then progressively less specific directory matches,
    and finally a wildcard '*' entry.
    """
    # Check for an exact match.
    if file_path in assignees_map:
        return set(assignee.lstrip("@") for assignee in assignees_map[file_path])

    # Check directory matches from most to least specific.
    parts = file_path.split("/")
    for i in range(len(parts), 0, -1):
        possible_path = "/".join(parts[:i])
        if possible_path in assignees_map:
            return set(
                assignee.lstrip("@") for assignee in assignees_map[possible_path]
            )

    # Check for a wildcard '*' mapping.
    if "*" in assignees_map:
        return set(assignee.lstrip("@") for assignee in assignees_map["*"])

    return set()


def find_common_assignees(changed_files, assignees_map):
    """
    Find the set of common assignees responsible for all changed files.
    If no common assignees exist, fall back to returning all unique assignees.
    """
    if not changed_files:
        return set()

    # Start with the assignees for the first file.
    common_assignees = get_assignees_for_path(changed_files[0], assignees_map)

    # Intersect with assignees from each subsequent file.
    for file in changed_files[1:]:
        file_assignees = get_assignees_for_path(file, assignees_map)
        common_assignees.intersection_update(file_assignees)
        if not common_assignees:
            break

    # Fallback: if no common assignees, return all unique assignees.
    if not common_assignees:
        all_assignees = set()
        for assignees in assignees_map.values():
            all_assignees.update(assignee.lstrip("@") for assignee in assignees)
        if all_assignees:
            print("No common assignees found. Assigning all possible assignees.")
            return all_assignees
        else:
            print("No assignees found in CODEOWNERS.")

    return common_assignees


def apply_labels(repo, pr_number, labels):
    """Apply the determined labels to the pull request."""
    try:
        issue = repo.get_issue(pr_number)
        current_labels = [label.name for label in issue.labels]
        new_labels = list(set(current_labels + list(labels)))
        issue.set_labels(*new_labels)
        print(f"Successfully applied labels: {', '.join(new_labels)}")
    except Exception as e:
        raise GitHubLabelError(f"Failed to apply labels: {str(e)}")


def assign_assignees(repo, pr_number, assignees):
    """Assign the determined assignees to the pull request."""
    if not assignees:
        print("No assignees to assign.")
        return

    try:
        issue = repo.get_issue(pr_number)
        issue.add_to_assignees(*assignees)
        print(f"Successfully assigned: {', '.join(assignees)}")
    except Exception as e:
        print(f"Error: Failed to assign assignees: {e}")
        print(f"Attempted assignees: {assignees}")


def main():
    try:
        validate_environment()
        github_client = Github(GITHUB_TOKEN)
        repo = github_client.get_repo(REPO)
        pr_number_int = int(PR_NUMBER)

        # Retrieve the pull request and use its head branch for the CODEOWNERS file
        pull_request = repo.get_pull(pr_number_int)
        branch = pull_request.head.ref
        print(f"Using CODEOWNERS file from branch: {branch}")

        # Read CODEOWNERS and filters
        valid_labels, assignees_map = read_codeowners(repo, branch=branch)
        filter_data = read_filter_yml()

        # Get changed files from the pull request
        changed_files = [file.filename for file in pull_request.get_files()]
        print(f"Changed files in PR: {changed_files}")

        # Process files to determine which labels to apply
        labels = process_files(changed_files, valid_labels, filter_data)
        if labels:
            print(f"Found labels: {', '.join(labels)}")
            create_labels(repo, labels)
            apply_labels(repo, pr_number_int, labels)
        else:
            print("No matching labels found")

        # Determine and assign common assignees (or all if none are common)
        common_assignees = find_common_assignees(changed_files, assignees_map)
        if common_assignees:
            print(f"Found common assignees: {common_assignees}")
            assign_assignees(repo, pr_number_int, common_assignees)
        else:
            print("No assignees found")

    except Exception as e:
        print(f"Unexpected error: {e}")
        raise


if __name__ == "__main__":
    main()
