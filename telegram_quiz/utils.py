def assign_labels(options):
    labels = ["a)", "b)", "c)", "d)", "e)"]
    return [f"{labels[i]} {options[i][3:].strip()}" for i in range(len(options))]


def build_progress_bar(current, total, length=10):
    filled = int((current + 1) / total * length)
    return "█" * filled + "░" * (length - filled)
