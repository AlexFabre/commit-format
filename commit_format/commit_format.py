# pylint: disable=C0114
# pylint: disable=C0115
# pylint: disable=C0116
# pylint: disable=R0912
# pylint: disable=R0914
# pylint: disable=R0915

import argparse
import subprocess
import sys
import re
import tomllib
import os
from importlib.metadata import version, PackageNotFoundError
from urllib.parse import urlparse
from enum import IntFlag


def get_version() -> str:
    try:
        return version("commit_format")
    except PackageNotFoundError:
        return "dev"


# ANSI escape codes for colors
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
BLUE = "\033[94m"
RESET = "\033[0m"


class Error(IntFlag):
    """Error codes for commit format validation (bitmask flags)."""

    HEADER_PATTERN_MISMATCH = 0x01
    BODY_MISSING = 0x02
    FOOTER_MISSING = 0x04
    FOOTER_PATTERN_MISMATCH = 0x08
    SPELLING_MISTAKES = 0x10
    LINE_LENGTH = 0x20
    URL_FORMAT = 0x40


def is_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def contains_url(string: str) -> bool:
    if "/" not in string:
        return False

    # Split on '(', ')', '[', ']', and space ' '
    word_list = re.split(r"[()\[\]\s]", string)

    for w in word_list:
        if is_url(w):
            return True

    return False


class CommitFormat:
    def __init__(self, verbosity=False):
        self.verbosity = verbosity
        self.commit_template = None

    def error(self, text: str):
        """Prints the given text in red."""
        print(f"{RED}{text}{RESET}")

    def warning(self, text: str):
        """Prints the given text in yellow."""
        print(f"{YELLOW}{text}{RESET}")

    def highlight_words_in_txt(
        self, text: str, words="", highlight_color=f"{RED}"
    ) -> str:
        """Prints the given text and highlights the words in the list."""
        for word in words:
            word = self.remove_ansi_color_codes(word)
            text = text[::-1].replace(
                f"{word}"[::-1], f"{highlight_color}{word}{RESET}"[::-1], 1
            )[::-1]
        return text

    def remove_ansi_color_codes(self, text: str) -> str:
        ansi_escape_pattern = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")
        return ansi_escape_pattern.sub("", text)

    def info(self, text: str):
        """Prints the given text in blue."""
        print(text)

    def debug(self, text: str):
        """Prints the given text in green."""
        if self.verbosity:
            print(text)

    def get_current_branch(self) -> str:
        self.debug("get_current_branch: git rev-parse --abbrev-ref HEAD")
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()

    def list_unique_commits(self, current_branch, base_branch) -> list:
        if current_branch != base_branch:
            self.debug(
                "list_unique_commits: git log --pretty=format:%h "
                f"{base_branch}..{current_branch}"
            )
            result = subprocess.run(
                [
                    "git",
                    "log",
                    "--pretty=format:%h",
                    f"{base_branch}..{current_branch}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout.split()

        self.warning(
            f"Running on base branch {base_branch}. Use option -a to check base branch commits."
        )
        sys.exit(0)

    def list_all_commits(self) -> list:
        result = subprocess.run(
            ["git", "log", "--pretty=format:%h"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.split()

    def get_commit_message(self, commit_sha: str) -> str:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%B", commit_sha],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()

    def run_codespell(self, message: str) -> tuple:
        result = subprocess.run(
            ["codespell", "-c", "-", "-"],
            input=message,
            capture_output=True,
            text=True,
            check=False,
        )
        lines = result.stdout.strip().split("\n")
        selected_lines = [line for index, line in enumerate(lines) if index % 2 != 0]
        faulty_words = [line.split()[0] for line in selected_lines if line]
        return "\n".join(selected_lines), faulty_words

    def spell_check(self, commit: str, commit_message: str) -> int:
        spell_error = 0

        # Run codespell
        codespell_proposition, faulty_words = self.run_codespell(commit_message)
        if codespell_proposition:
            spell_error |= Error.SPELLING_MISTAKES
            self.warning(f"Commit {commit} has spelling mistakes")
            self.info(
                self.highlight_words_in_txt(f"---\n{commit_message}", faulty_words)
            )
            self.info(f"---\nCodespell fix proposition:\n{codespell_proposition}\n---")

        # Run another spelling tool:
        # ...

        return spell_error

    def lines_length(self, commit: str, commit_message: str, length_limit) -> int:

        if length_limit == 0:
            return 0

        length_exceeded = 0
        line_number = 0
        url_format_error = False

        # This variable will handle the full commit message.
        # It's a line by line aggregation with the problematic words highlighted in RED.
        highlighted_commit_message = ""

        # Split the commit message into lines
        lines = commit_message.split("\n")

        # Check if any line exceeds the length limit
        for line in lines:
            line_number += 1
            removed_words = []

            if line_number > 1:
                # A line return must be manually added at the beginning of new lines
                # to rebuild the commit message.
                highlighted_commit_message += "\n"

            line_length = len(line)
            if line_length > length_limit:
                if contains_url(line):
                    # Check for lines containing URLs
                    if is_url(line.split()[-1]):
                        if len(line.split()) == 2:
                            # Comply with expected format for URL:
                            # [index] url://...
                            continue
                    url_format_error = True

                length_exceeded += 1

                line_copy = line
                # Split the line into words
                while len(line_copy) > length_limit:
                    # Find the last space in the line
                    last_space_index = line_copy.rfind(" ")

                    removed_word = line_copy[(last_space_index + 1) :]
                    removed_words.append(removed_word)

                    # Remove the last word by slicing up to the last space (if there was any space)
                    if last_space_index == -1:
                        line_copy = ""
                    else:
                        line_copy = line_copy[:last_space_index]

            highlighted_commit_message += (
                f"{self.highlight_words_in_txt(line, removed_words)}"
            )

        err = 0
        if length_exceeded:
            if url_format_error is True:
                self.warning(f"Commit {commit}: bad URL format:\n[index] url://...")
                err = Error.URL_FORMAT
            else:
                self.warning(f"Commit {commit}: exceeds {length_limit} chars limit")
                err = Error.LINE_LENGTH
            self.info(f"---\n{highlighted_commit_message}\n---")

        return err

    def load_template(self, template_path: str):
        if os.path.isfile(template_path):
            with open(template_path, mode="rb") as f:
                data = tomllib.load(f)

            self.commit_template = data
        else:
            self.error(f"Template file not found or unreadable: {template_path}")
            sys.exit(2)

    def split_message(self, message: str, has_footer: bool):
        """
        Splits a message into its header, body, and footer components.

        This function processes a multi-line message string and separates it into
        three parts: the header, the body, and the footer.
        1. The header is the first line(s) of the message until two consecutive
           line breaks are detected.
        2. Then, if `has_footer` option is set to 'True', the function identifies
           the last non-empty line as the footer.
        3. Finally, the body consists of all lines after the header, excluding the
           footer, if it exists.

        Args:
            message (str): The multi-line message to be split.
            has_footer (bool): A flag indicating whether the message contains a footer.

        Returns:
            tuple: A tuple containing four elements:
                - header (str): The first line(s) of the commit message.
                - body (list of str): A list of lines representing the body of the message.
                - footer (str): The footer line if present.
                - lines (list of str): A list of all lines in the original message.

        """
        lines = message.splitlines()

        if not lines:
            return "", [], "", lines

        line_cnt = len(lines)
        footer_start = line_cnt
        header = lines[0]

        i = 1
        while i < len(lines) and lines[i] != "":
            header += " " + lines[i]
            i += 1
        body_start = i

        if has_footer:
            # Identify the last non-empty line as the potential footer
            i = line_cnt - 1
            while i > 0 and not lines[i].strip():
                i -= 1
            if i > 0:
                footer_start = i

        # Determine the body by excluding the header and footer
        body = lines[body_start:footer_start] if line_cnt > 1 else []
        footer = lines[footer_start] if footer_start < line_cnt else ""

        self.debug(
            f"--HEADER--\n{header}\n---BODY---\n{body}\n--FOOTER--\n{footer}\n----------"
        )

        return header, body, footer, lines

    def template_check(self, commit: str, commit_message: str) -> int:
        if not self.commit_template:
            return 0

        errors = 0
        template = self.commit_template

        footer_required = False

        try:
            footer_required = template["footer"]["pattern"]
        except KeyError:
            pass

        header, body, footer, *_ = self.split_message(commit_message, footer_required)

        # Header checks

        try:
            pattern = template["header"]["pattern"]
            if not re.match(pattern, header):
                errors |= Error.HEADER_PATTERN_MISMATCH
                self.warning(f"Commit {commit}: header does not match required pattern")
                self.info(f"Header: '{header}'")
                self.info(f"Expected pattern: {pattern}")
        except KeyError:
            pass

        # Body check
        body_required = False
        try:
            body_required = template["body"]["allow_empty"]
            body_required = not body_required
        except KeyError:
            pass

        try:
            body_required = template["body"]["required"]
        except KeyError:
            pass

        if body_required:
            body_has_content = any(line.strip() != "" for line in body)
            if not body_has_content:
                errors |= Error.BODY_MISSING
                self.warning(f"Commit {commit}: commit body is empty")

        # Footer checks
        if footer_required and footer == "":
            errors |= Error.FOOTER_MISSING
            self.warning(f"Commit {commit}: missing required footer section")

        # Footer line pattern
        if footer_required and footer != "":
            try:
                fpattern = template["footer"]["pattern"]
                compiled = re.compile(fpattern)
                if not compiled.match(footer):
                    errors |= Error.FOOTER_PATTERN_MISMATCH
                    self.warning(f"Commit {commit}: footer line does not match pattern")
                    self.info(f"Footer: '{footer}'")
                    self.info(f"Expected pattern: {fpattern}")
            except KeyError:
                pass

        return errors


def find_config_file() -> str | None:
    """Auto-discover config file in current directory or git root."""
    candidates = [".commit-format", ".commit-format.toml"]

    # Check current directory first
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    # Check git root directory
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            git_root = result.stdout.strip()
            for candidate in candidates:
                path = os.path.join(git_root, candidate)
                if os.path.isfile(path):
                    return path
    except FileNotFoundError:
        pass

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Perform various checks on commit messages."
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {get_version()}"
    )
    parser.add_argument(
        "-ns",
        "--no-spelling",
        action="store_true",
        help="disable checking misspelled words",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=72,
        help="commit lines maximum length. Default: '72' ('0' => no line limit)",
    )
    parser.add_argument(
        "-t",
        "--template",
        type=str,
        default=None,
        help="path to a commit-format template file to validate header/body/footer "
        "commit message structure",
    )
    parser.add_argument(
        "-b",
        "--base",
        type=str,
        default="main",
        help="name of the base branch. Default 'main'",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="check all commits (including base branch commits)",
    )
    parser.add_argument(
        "-v", "--verbosity", action="store_true", help="increase output verbosity"
    )
    args = parser.parse_args()

    commit_format = CommitFormat(verbosity=args.verbosity)

    template_path = args.template
    if not template_path:
        template_path = find_config_file()
        if template_path:
            commit_format.debug(f"Auto-discovered config: {template_path}")

    commit_format.info(f"Using config file: {template_path}")

    if template_path:
        commit_format.load_template(template_path)

    error_found = 0
    current_branch = commit_format.get_current_branch()
    if not current_branch:
        commit_format.error("Not inside an active git repository")
        sys.exit(1)

    if args.all is True:
        commit_list = commit_format.list_all_commits()
    else:
        commit_list = commit_format.list_unique_commits(current_branch, args.base)

    if not commit_list:
        commit_format.error(
            f"Error:{RESET} branch {GREEN}{current_branch}{RESET} "
            f"has no diff commit with base branch {GREEN}{args.base}{RESET}"
        )
        sys.exit(1)

    commit_format.debug(
        f"Checking {GREEN}{len(commit_list)}{RESET} "
        "commits on branch {GREEN}{current_branch}{RESET}"
    )

    pass_count = 0

    for commit in commit_list:
        error_on_commit = 0
        commit_message = commit_format.get_commit_message(commit)
        if args.no_spelling is False:
            error_on_commit += commit_format.spell_check(commit, commit_message)

        error_on_commit += commit_format.lines_length(
            commit, commit_message, args.limit
        )
        if commit_format.commit_template is not None:
            error_on_commit += commit_format.template_check(commit, commit_message)

        if not error_on_commit:
            commit_format.info(f"{GREEN}Commit {commit} OK{RESET}")
            pass_count += 1
        else:
            error_found += error_on_commit

    # Summary
    print(
        f"{pass_count}/{len(commit_list)} commits passed, {len(commit_list) - pass_count} failed"
    )

    # Warnings for deprecated options:
    if (
        commit_format.commit_template
        and "allow_empty" in commit_format.commit_template.get("body", {})
    ):
        commit_format.warning(
            "Template option 'Body::allow_empty' is deprecated. Use 'Body::required' instead"
        )

    sys.exit(error_found)


if __name__ == "__main__":
    main()
