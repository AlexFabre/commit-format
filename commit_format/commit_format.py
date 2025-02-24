import argparse
import subprocess
import re
from urllib.parse import urlparse

# ANSI escape codes for colors
RED = '\033[91m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
BLUE = '\033[94m'
RESET = '\033[0m'

def is_url(url):
  try:
    result = urlparse(url)
    return all([result.scheme, result.netloc])
  except ValueError:
    return False

class CommitFormat:
    def __init__(self, verbosity=False):
        self.verbosity = verbosity

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
            text = text[::-1].replace(f"{word}"[::-1], f"{highlight_color}{word}{RESET}"[::-1], 1)[::-1]
        
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
        result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True)
        return result.stdout.strip()

    def list_unique_commits(self, current_branch, base_branch) -> list:
        if current_branch != base_branch:
            result = subprocess.run(['git', 'log', '--pretty=format:%h', f'{base_branch}..{current_branch}'], capture_output=True, text=True)
            return result.stdout.split()
        else:
            self.error(f"Running on branch {base_branch}. Abort checking commits.")
            exit(0)
    
    def list_all_commits(self) -> list:
            result = subprocess.run(['git', 'log', '--pretty=format:%h'], capture_output=True, text=True)
            return result.stdout.split()

    def get_commit_message(self, commit_sha: str) -> str:
        result = subprocess.run(['git', 'show', '-s', '--format=%B', commit_sha], capture_output=True, text=True)
        return result.stdout.strip()

    def run_codespell(self, message: str) -> tuple:
        result = subprocess.run(['codespell', '-c', '-', '-'], input=message, capture_output=True, text=True)
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
        # It's a line by line agregation with the problematic words highlighted in RED.
        highlighted_commit_message = ""
    
        # Split the commit message into lines
        lines = commit_message.split('\n')
    
        # Check if any line exceeds the length limit
        for line in lines:
            line_number += 1
            removed_words = []

            if (line_number > 1):
                # A line return must be manually added at the begining of new lines
                # to rebuild the commit message.
                highlighted_commit_message += "\n"

            line_length = len(line)
            if line_length > length_limit:

                # Check for lines containing URLs
                if is_url(line.split()[-1]):
                    if len(line.split()) == 2:
                        # Expected format for URL: [index] url://...
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
        
        if (length_exceeded):
            self.warning(f"Commit {commit}: exceeds {length_limit} chars limit")
            self.info(f"---\n{highlighted_commit_message}\n---")
            if (url_format_error == True):
                self.warning("---\nURL format:\n[index] url://...\n---")
    
        return length_exceeded
    


def main():
    parser = argparse.ArgumentParser(description="Perform various checks on commit messages.")
    parser.add_argument('-l', '--lineslimit', type=int, default=0, help="message line max length. Default: '0' (no line limit)")
    parser.add_argument('-b', '--base', type=str, default="main", help="name of the base branch. Default 'main")
    parser.add_argument('-a', '--all', action='store_true', help="force check on all commits (including base branch commits)")
    parser.add_argument('-v', '--verbosity', action='store_true', help="increase output verbosity")
    args = parser.parse_args()

    commit_format = CommitFormat(verbosity=args.verbosity)

    error_found = 0
    current_branch = commit_format.get_current_branch()
    if not current_branch:
        commit_format.error("Not inside an active git repository")
        exit(1)

    if args.all == True:
        commit_list = commit_format.list_all_commits()
    else:
        commit_list = commit_format.list_unique_commits(current_branch, args.base)
    
    if not commit_list:
        commit_format.error(f"Error:{RESET} branch {GREEN}{current_branch}{RESET} has no diff commit with base branch {GREEN}{args.base}{RESET}")
        exit(1)

    commit_format.debug(f"Checking {GREEN}{len(commit_list)}{RESET} commits on branch {GREEN}{current_branch}{RESET}")

    for commit in commit_list:
        error_on_commit = 0
        commit_message = commit_format.get_commit_message(commit)
        error_on_commit += commit_format.spell_check(commit, commit_message)
        error_on_commit += commit_format.lines_length(commit, commit_message, args.lineslimit)

        if not error_on_commit:
            commit_format.info(f"{GREEN}Commit {commit} OK{RESET}")
        else:
            error_found += error_on_commit
            
    exit(error_found)

if __name__ == '__main__':
    main()
