import os
from github import Github

# Get environment variables
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")
PR_NUMBER = int(os.getenv("GITHUB_PR_NUMBER"))

# Define size labels, their ranges, and colors
size_labels = {
    "XS": ((0, 20), "388E3C"),
    "S": ((20, 50), "4CAF50"),
    "M": ((50, 100), "FFEB3B"),
    "L": ((100, 500), "FF9800"),
    "XL": ((500, 1000), "F44336"),
    "XXL": ((1000, float("inf")), "B71C1C"),
}

# Initialize GitHub client
gh = Github(GITHUB_TOKEN)
repo = gh.get_repo(REPO_NAME)
pr = repo.get_pull(PR_NUMBER)


def get_changed_lines():
    files = pr.get_files()
    changed_lines = sum(f.additions + f.deletions for f in files)
    print(f"Total changed lines: {changed_lines}")
    return changed_lines


def determine_size_label(changed_lines):
    for label, (range_values, _) in size_labels.items():
        min_lines, max_lines = range_values
        if min_lines <= changed_lines <= max_lines:
            return label
    return None


def remove_existing_size_labels(correct_label):
    labels_to_remove = [
        label.name
        for label in pr.get_labels()
        if label.name in size_labels and label.name != correct_label
    ]
    for label in labels_to_remove:
        pr.remove_from_labels(label)
        print(f"Removed label: {label}")


def assign_label(label):
    color = size_labels[label][1]
    existing_labels = {
        label_obj.name: label_obj.color for label_obj in repo.get_labels()
    }
    current_labels = [label_obj.name for label_obj in pr.get_labels()]

    # Check if the correct label is already assigned
    if label in current_labels:
        print(f"Label '{label}' is already assigned. Skipping.")
        return

    # Check if the label exists with the correct color
    if label not in existing_labels:
        # Create the label if it doesn't exist
        repo.create_label(name=label, color=color)
        print(f"Created label: {label} with color: {color}")
    elif existing_labels[label] != color:
        # Update the color if it exists but with a different color
        repo.get_label(label).edit(name=label, color=color)
        print(f"Updated label color: {label} to {color}")

    # Add label to the PR
    pr.add_to_labels(label)
    print(f"Assigned label: {label}")


if __name__ == "__main__":
    changed_lines = get_changed_lines()
    size_label = determine_size_label(changed_lines)

    if size_label:
        remove_existing_size_labels(size_label)
        assign_label(size_label)
    else:
        print("No size label determined.")
