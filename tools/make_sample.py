"""Writes a data file that holds the app's built-in sample, for screenshots and manual checks.

Usage: python -X utf8 tools/make_sample.py <folder> [en|ko]
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402
import i18n  # noqa: E402


def main():
    folder, lang = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "en")
    data = core.new_data()
    data["settings"]["lang"] = lang
    core.load_sample(data, i18n.SAMPLE[lang], datetime.now())
    os.makedirs(folder, exist_ok=True)
    core.save(os.path.join(folder, core.DATA_FILE), data)
    print(f"wrote {len(data['items'])} items to {folder}")


if __name__ == "__main__":
    main()
