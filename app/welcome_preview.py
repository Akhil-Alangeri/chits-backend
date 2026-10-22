"""Generate fictional sample artifacts without loading database settings or sending mail."""
import argparse
from pathlib import Path

from app.services.welcome_template import render_welcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="previews")
    args = parser.parse_args()
    directory = Path(args.output)
    directory.mkdir(parents=True, exist_ok=True)
    subject, text, html = render_welcome("Ananya Rao", "Lotus Chit Company (Sample)",
                                         "Lotus Community Group (Sample)", "confirmed")
    (directory / "membership-welcome.html").write_text(html, encoding="utf-8")
    (directory / "membership-welcome.txt").write_text(subject + "\n\n" + text, encoding="utf-8")
    print(f"Fictional preview generated in {directory}")


if __name__ == "__main__":
    main()
