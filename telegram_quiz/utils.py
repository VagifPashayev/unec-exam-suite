def assign_labels(options):
    """Compatibility helper for the desktop/web-era tests."""

    labels = [f"{letter})" for letter in "abcdefghijklmnopqrstuvwxyz"]
    return [f"{labels[index]} {option[3:].strip()}" for index, option in enumerate(options)]


def build_progress_bar(current, total, length=10):
    if total <= 0 or length <= 0:
        return ""
    completed = min(max(current + 1, 0), total)
    filled = int(completed / total * length)
    return "█" * filled + "░" * (length - filled)
