"""
Check the performance requirement: results should appear within 10 seconds.

    python measure_performance.py

It runs the real app.py through Streamlit's testing tool and times two things:
submitting a completed assessment, and uploading each dataset on the Dataset
tab, from the moment the button is pressed or the file is uploaded until the
results have been built. It runs on your own device, so the network delay of
the deployed link is not included.
"""

import logging
import os
import time

from streamlit.testing.v1 import AppTest

from src import score_configuration as cfg

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app.py")
LIMIT = 10.0

# Change the paths here if your files are named differently.
DATASETS = [
    ("Survey dataset (Google Forms)", "data/AI Adoption Readiness Survey (Responses).xlsx"),
    ("Real dataset", "data/AI adoption Survey (Responses).xlsx"),
    ("Synthetic dataset", "data/synthetic_companies_readable.csv",),
]

# Streamlit prints a harmless warning about a missing run context when it is
# driven outside "streamlit run". It would bury the results, so it's hidden.
logging.disable(logging.WARNING)


def show(label, seconds):
    result = "Pass" if seconds < LIMIT else "Fail"
    print(f"{label:<45} {seconds:6.2f} s   {result}")


def time_assessment():
    app = AppTest.from_file(APP, default_timeout=120).run()
    for field, options in cfg.CATEGORICAL_FIELDS.items():
        app.session_state[f"ctx_{field}"] = options[0]
    for item in cfg.ALL_ITEMS:
        app.session_state[f"item_{item.id}"] = 3
    app.run()

    start = time.perf_counter()
    app.button[0].click().run()
    seconds = time.perf_counter() - start

    if "results" not in app.session_state:
        print("The assessment did not produce results, so this timing is not valid.")
    return seconds


def time_dataset(path):
    with open(path, "rb") as handle:
        content = handle.read()

    app = AppTest.from_file(APP, default_timeout=120).run()

    start = time.perf_counter()
    app.file_uploader[0].upload(os.path.basename(path), content).run()

    # A dataset from a different questionnaire (like the Zenodo one) first
    # shows a comparison. Its results only appear once "Score the covered
    # factors" is ticked, so that step is included in the time.
    boxes = [box for box in app.checkbox if box.label == "Score the covered factors"]
    if boxes:
        boxes[0].check().run()
    seconds = time.perf_counter() - start

    if not any(metric.label == "Mean readiness" for metric in app.metric):
        print(f"No results appeared for {os.path.basename(path)}, so this timing is not valid.")
    return seconds


def main():
    print(f"{'Step':<45} {'Time':>8}   Under {LIMIT:.0f} s?")
    show("Submit a completed assessment", time_assessment())

    for label, relative in DATASETS:
        path = os.path.join(HERE, relative)
        if not os.path.exists(path):
            print(f"{label:<45} skipped, file not found: {relative}")
            continue
        show(f"Upload {label}", time_dataset(path))


if __name__ == "__main__":
    main()
