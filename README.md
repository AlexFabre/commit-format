# commit-format
A tool to format git commit messages.

## Supported checkers

- Check that each message lines does not exceed a length limit. The option `-l <int>` allow custom length (default 80 chars).
- Check that codespell does not find any spelling mistake on commit messages.

## Installation

```sh
$ pip install git+https://github.com/AlexFabre/commit-format
```

## Options

```sh
$ commit-format --help
usage: commit_format.py [-h] [-l LINESLIMIT] [-v]

Various checks on commit messages.

options:
  -h, --help            show this help message and exit
  -l, --lineslimit LINESLIMIT
                        commit message lines max length. (Default 80)
  -v, --verbosity       increase output verbosity
```
