# commit-format

A tool to check your commit messages format.

## Supported checkers

Primarily disigned for to check for spelling mistakes in commit messages,
`commit-format` now comes with various checker allowing to:

- Check that each message lines does not exceed a length limit.
- Check for spelling mistake on commit messages.
- `NEW` Check commit header/body/footer against a defined template.

## Installation

```sh
pip install commit-format
```

Help command will show you all availables options:

```sh
commit-format --help
```

## Format options

### `-l`, `--limit` Line limit check

You can check that every line in the commit message (including the title/header)
does not exceed a length limit. By default the value is set to `72`.

A limit of '0' `--limit 0` will disable the line limit checker.

Usage:

```sh
commit-format -l 80
```

> URL in the commit body will not trigger any length warnings if it
> adheres to the expected format.
>
> ```txt
> my commit message has a ref[1]
> ...
>
> [1] url://...
> ```

### `-ns`, `--no-spelling` Disable spelling mistake

By default, `commit-format` checks for common spelling mistakes in the commit
messages. This option rely on `codespell` and may produce some false-positive
results. This new option `-ns` `--no-spelling` let the user disable the
spelling checker.

```sh
commit-format -ns
```

### `-t`, `--template` Template compliance

You can provide a configuration TOML file template to validate the commit
header/footer format and required symbols.

Usage:

```sh
commit-format -t /path/to/.commit-format
```

Template schema (TOML):

- [header]
  - pattern: Regex that the first line (header) must match.
- [body]
  - allow_empty: true/false to allow a commit with only a header (no body).
  - blank_line_after_header: true/false to enforce a blank line between header
  and body.
- [footer]
  - required: true/false to require a footer section.
  - pattern: Regex that each footer line must match.

Example `.commit-format`:

```toml
[header]
# header line regex:
pattern = ^(feat: |fic: |ci: |doc: ).+$

[body]
# Allow empty body commit message. (i.e. single line commit message).
allow_empty = false
# Require that header line and body line are separated by an empty line.
blank_line_after_header = true

[footer]
# Require a footer line
required = true
# Footer line regex
pattern = ^(Signed-off-by: ).+$

```

## Behavior option

### `-a`, `--all` Force checking all commits

By default the script will only run on a branch and stop when reaching the base
branch. If run on a base branch directly, the script will throw an error:

```sh
Running on branch main. Abort checking commits.
```

This measure is there to prevent running the script over past commits.

If running on 'main'/'master' is required, option `-a` will force the script
to run regadless the branch name.

Usage:

```sh
commit-format -a
```

### `-b`, `--base` Base branch name

You can set the base branch name according to your project.  
As described in `option -a` section the base branch name is required to let the
script restrict it's analysis on the commits of a branch. Default value for the
base branch name is `main`.  

> When running this script in a CI environment, you may be required to fetch your
> base branch manually.
> See [github workflow](.github/workflows/commit-format.yml) example.

Usage:

```sh
commit-format -b origin/main
```

### `-v`, `--verbosity`

Display debug messages from the script.
