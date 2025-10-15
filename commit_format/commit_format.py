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
import configparser
from urllib.parse import urlparse

# ANSI escape codes for colors
RED = '\033[91m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
BLUE = '\033[94m'
RESET = '\033[0m'

def is_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def contains_url(string: str) -> bool:
    if '/' not in string:
        return False

    # Split on '(', ')', '[', ']', and space ' '
    word_list = re.split(r'[()\[\]\s]', string)

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

    def highlight_words_in_txt(self, text: str, words="", highlight_color=f"{RED}") -> str:
        """Prints the given text and highlights the words in the list."""
        for word in words:
            word = self.remove_ansi_color_codes(word)
            text = text[::-1].replace(f"{word}"[::-1],
                                      f"{highlight_color}{word}{RESET}"[::-1], 1)[::-1]
        return text

    def remove_ansi_color_codes(self, text: str) -> str:
        ansi_escape_pattern = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
        return ansi_escape_pattern.sub('', text)

    def info(self, text: str):
        """Prints the given text in blue."""
        print(text)

    def debug(self, text: str):
        """Prints the given text in green."""
        if self.verbosity:
            print(text)

    def get_current_branch(self) -> str:
        self.debug("get_current_branch: git rev-parse --abbrev-ref HEAD")
        result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                capture_output=True, text=True, check=False)
        return result.stdout.strip()

    def list_unique_commits(self, current_branch, base_branch) -> list:
        if current_branch != base_branch:
            self.debug("list_unique_commits: git log --pretty=format:%h "
                       f"{base_branch}..{current_branch}")
            result = subprocess.run(['git', 'log', '--pretty=format:%h',
                                     f'{base_branch}..{current_branch}'],
                                     capture_output=True,
                                     text=True, check=False)
            return result.stdout.split()

        self.error(f"Running on branch {base_branch}. Abort checking commits.")
        sys.exit(0)

    def list_all_commits(self) -> list:
        result = subprocess.run(['git', 'log', '--pretty=format:%h'],
                                capture_output=True, text=True, check=False)
        return result.stdout.split()

    def get_commit_message(self, commit_sha: str) -> str:
        result = subprocess.run(['git', 'show', '-s', '--format=%B', commit_sha],
                                capture_output=True,
                                text=True, check=False)
        return result.stdout.strip()

    def run_codespell(self, message: str) -> tuple:
        result = subprocess.run(['codespell', '-c', '-', '-'], input=message,
                                capture_output=True,
                                text=True, check=False)
        lines = result.stdout.strip().split('\n')
        selected_lines = [line for index, line in enumerate(lines) if index % 2 != 0]
        faulty_words = [line.split()[0] for line in selected_lines if line]
        return '\n'.join(selected_lines), faulty_words

    def spell_check(self, commit: str, commit_message: str) -> bool:
        spell_error = 0

        # Run codespell
        codespell_proposition, faulty_words = self.run_codespell(commit_message)
        if codespell_proposition:
            spell_error += 1
            self.warning(f"Commit {commit} has spelling mistakes")
            self.info(self.highlight_words_in_txt(f"---\n{commit_message}", faulty_words))
            self.info(f"---\nCodespell fix proposition:\n{codespell_proposition}\n---")

        # Run another spelling tool:
        # ...

        return spell_error

    def lines_length(self, commit: str, commit_message: str, length_limit) -> bool:

        if length_limit == 0:
            return 0

        length_exceeded = 0
        line_number = 0
        url_format_error = False

        # This variable will handle the full commit message.
        # It's a line by line aggregation with the problematic words highlighted in RED.
        highlighted_commit_message = ""

        # Split the commit message into lines
        lines = commit_message.split('\n')

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
                    last_space_index = line_copy.rfind(' ')

                    removed_word = line_copy[(last_space_index+1):]
                    removed_words.append(removed_word)

                    # Remove the last word by slicing up to the last space (if there was any space)
                    if last_space_index == -1:
                        line_copy = ""
                    else:
                        line_copy = line_copy[:last_space_index]

            highlighted_commit_message += f"{self.highlight_words_in_txt(line, removed_words)}"

        if length_exceeded:
            if url_format_error is True:
                self.warning(f"Commit {commit}: bad URL format:\n[index] url://...")
            else:
                self.warning(f"Commit {commit}: exceeds {length_limit} chars limit")
            self.info(f"---\n{highlighted_commit_message}\n---")

        return length_exceeded

    def load_template(self, template_path: str):
        cfg = configparser.ConfigParser()
        read = cfg.read(template_path)
        if not read:
            self.error(f"Template file not found or unreadable: {template_path}")
            sys.exit(2)
        self.commit_template = cfg

    def _split_message(self, message: str, has_footer: bool):
        """
        Splits a message into its header, body, and footer components.

        This function processes a multi-line message string and separates it into
        three parts: the header, the body, and the footer. The header is always the
        first line of the message. If `has_footer` is True, the function attempts to
        identify the last non-empty line as the footer. The body consists of all lines
        between the header and the footer.

        Args:
            message (str): The multi-line message to be split.
            has_footer (bool): A flag indicating whether the message contains a footer.

        Returns:
            tuple: A tuple containing four elements:
                - header (str): The first line of the message.
                - body (list of str): A list of lines representing the body of the message.
                - footers (list of str): A list containing the footer line if present.
                - lines (list of str): A list of all lines in the original message.

        """
        lines = message.splitlines()
        line_cnt = len(lines)
        footer_start = line_cnt
        header = lines[0] if lines else ""

        if has_footer:
            # Identify the last non-empty line as the potential footer
            i = line_cnt - 1
            while i > 0 and lines[i].strip() == "":
                i -= 1

            footer_start = i if i > 0 else line_cnt

        # Determine the body by excluding the header and footer
        body = lines[1:footer_start] if line_cnt > 1 else []
        footers = [lines[footer_start]] if footer_start < line_cnt else []

        self.debug(f'--HEADER--\n{header}\n---BODY---\n{body}\n--FOOTER--\n{footers}\n----------')

        return header, body, footers, lines

    def template_check(self, commit: str, commit_message: str) -> int:
        if not self.commit_template:
            return 0

        errors = 0
        cfg = self.commit_template

        footer_required = False
        if cfg.has_section('footer') and cfg.has_option('footer', 'required'):
            try:
                footer_required = cfg.getboolean('footer', 'required')
            except ValueError:
                footer_required = False

        header, body, footers, all_lines = self._split_message(commit_message, footer_required)

        # Header checks
        if cfg.has_section('header') and cfg.has_option('header', 'pattern'):
            pattern = cfg.get('header', 'pattern')
            if not re.match(pattern, header):
                errors += 1
                self.warning(f"Commit {commit}: header does not match required pattern")
                self.info(f"Header: '{header}'")
                self.info(f"Expected pattern: {pattern}")

        # Body separation check

        blank_after_header = False
        if cfg.has_section('body') and cfg.has_option('body', 'blank_line_after_header'):
            try:
                blank_after_header = cfg.getboolean('body', 'blank_line_after_header')
            except ValueError:
                blank_after_header = False

        if blank_after_header and len(all_lines) > 1:
            if all_lines[1].strip() != "":
                errors += 1
                self.warning(f"Commit {commit}: missing blank line after header")

        # Body emptiness check
        allow_empty = True
        if cfg.has_section('body') and cfg.has_option('body', 'allow_empty'):
            try:
                allow_empty = cfg.getboolean('body', 'allow_empty')
            except ValueError:
                allow_empty = True

        if not allow_empty:
            body_has_content = any(line.strip() != "" for line in body)
            if not body_has_content:
                errors += 1
                self.warning(f"Commit {commit}: commit body is empty")

        # Footer checks
        if footer_required and len(footers) == 0:
            errors += 1
            self.warning(f"Commit {commit}: missing required footer section")

        # Footer line pattern
        if (footer_required and len(footers) > 0
            and cfg.has_section('footer')
            and cfg.has_option('footer', 'pattern')):
            fpattern = cfg.get('footer', 'pattern')
            compiled = re.compile(fpattern)
            for line in footers:
                if line.strip() == "":
                    continue
                if not compiled.match(line):
                    errors += 1
                    self.warning(f"Commit {commit}: footer line does not match pattern")
                    self.info(f"Line: '{line}'")
                    self.info(f"Expected pattern: {fpattern}")

        return errors

def main():
    parser = argparse.ArgumentParser(description="Perform various checks on commit messages.")
    parser.add_argument('-ns', '--no-spelling',
                        action='store_true',
                        help="disable checking misspelled words")
    parser.add_argument('-l', '--limit',
                        type=int,
                        default=72,
                        help="commit lines maximum length. Default: '72' ('0' => no line limit)")
    parser.add_argument('-t', '--template',
                        type=str,
                        default=None,
                        help="path to a commit-format template file to validate header/body/footer "
                        "commit message structure")
    parser.add_argument('-b', '--base',
                        type=str,
                        default="main",
                        help="name of the base branch. Default 'main'")
    parser.add_argument('-a', '--all',
                        action='store_true',
                        help="check all commits (including base branch commits)")
    parser.add_argument('-v', '--verbosity',
                        action='store_true',
                        help="increase output verbosity")
    args = parser.parse_args()

    commit_format = CommitFormat(verbosity=args.verbosity)

    if args.template:
        commit_format.load_template(args.template)

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
        commit_format.error(f"Error:{RESET} branch {GREEN}{current_branch}{RESET} "
                            f"has no diff commit with base branch {GREEN}{args.base}{RESET}")
        sys.exit(1)

    commit_format.debug(f"Checking {GREEN}{len(commit_list)}{RESET} "
                        "commits on branch {GREEN}{current_branch}{RESET}")

    for commit in commit_list:
        error_on_commit = 0
        commit_message = commit_format.get_commit_message(commit)
        if args.no_spelling is False:
            error_on_commit += commit_format.spell_check(commit, commit_message)
        error_on_commit += commit_format.lines_length(commit, commit_message, args.limit)
        if commit_format.commit_template is not None:
            error_on_commit += commit_format.template_check(commit, commit_message)

        if not error_on_commit:
            commit_format.info(f"{GREEN}Commit {commit} OK{RESET}")
        else:
            error_found += error_on_commit

    sys.exit(error_found)

if __name__ == '__main__':
    main()
