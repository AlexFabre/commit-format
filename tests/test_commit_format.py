# pylint: disable=C0114
# pylint: disable=C0115
# pylint: disable=C0116
# pylint: disable=R0903

import pytest

from commit_format.commit_format import (
    is_url,
    contains_url,
    CommitFormat,
    find_config_file,
    get_version,
    Error,
)


class TestIsUrl:
    def test_valid_https_url(self):
        assert is_url("https://github.com/user/repo") is True

    def test_valid_http_url(self):
        assert is_url("http://example.com") is True

    def test_valid_url_with_path(self):
        assert is_url("https://example.com/path/to/resource") is True

    def test_invalid_url_no_scheme(self):
        assert is_url("example.com") is False

    def test_invalid_url_no_netloc(self):
        assert is_url("https://") is False

    def test_plain_text(self):
        assert is_url("just some text") is False

    def test_empty_string(self):
        assert is_url("") is False

    def test_file_path(self):
        assert is_url("/path/to/file") is False


class TestContainsUrl:
    def test_line_with_url(self):
        assert contains_url("Check this https://example.com for details") is True

    def test_line_without_url(self):
        assert contains_url("This is just plain text") is False

    def test_url_in_parentheses(self):
        assert contains_url("See (https://example.com) for more") is True

    def test_url_in_brackets(self):
        assert contains_url("[1] https://example.com") is True

    def test_no_slash_quick_exit(self):
        assert contains_url("no slashes here") is False

    def test_path_not_url(self):
        assert contains_url("see src/main.py for details") is False


class TestCommitFormatInit:
    def test_default_verbosity(self):
        cf = CommitFormat()
        assert cf.verbosity is False
        assert cf.commit_template is None

    def test_verbosity_enabled(self):
        cf = CommitFormat(verbosity=True)
        assert cf.verbosity is True


class TestSplitMessage:
    def test_header_only(self):
        cf = CommitFormat()
        header, body, footer, lines = cf.split_message("fix: simple fix", False)
        assert header == "fix: simple fix"
        assert body == []
        assert footer == ""
        assert lines == ["fix: simple fix"]

    def test_header_and_body(self):
        cf = CommitFormat()
        message = "fix: bug fix\n\nThis fixes the bug in the parser."
        header, body, footer, lines = cf.split_message(message, False)
        assert header == "fix: bug fix"
        assert body == ["", "This fixes the bug in the parser."]
        assert footer == ""
        assert len(lines) == 3

    def test_header_body_and_footer(self):
        cf = CommitFormat()
        message = (
            "feat: new feature\n\nAdded new functionality.\n\nSigned-off-by: Author"
        )
        header, body, footer, lines = cf.split_message(message, True)
        assert header == "feat: new feature"
        assert body == ["", "Added new functionality.", ""]
        assert footer == "Signed-off-by: Author"
        assert len(lines) == 5

    def test_footer_with_trailing_empty_lines(self):
        cf = CommitFormat()
        message = "fix: bug\n\nBody text.\n\nSigned-off-by: Author\n\n"
        header, body, footer, lines = cf.split_message(message, True)
        assert header == "fix: bug"
        assert body == ["", "Body text.", ""]
        assert footer == "Signed-off-by: Author"
        assert len(lines) == 6

    def test_multi_line_header(self):
        cf = CommitFormat()
        message = "fix: bug\nheader line 2\n\nBody text.\nSigned-off-by: Author\n\n"
        header, body, footer, lines = cf.split_message(message, True)
        assert header == "fix: bug header line 2"
        assert body == ["", "Body text."]
        assert footer == "Signed-off-by: Author"
        assert len(lines) == 6

    def test_empty_message(self):
        cf = CommitFormat()
        header, body, footer, lines = cf.split_message("", False)
        assert header == ""
        assert body == []
        assert footer == ""
        assert len(lines) == 0


class TestLinesLength:
    def test_all_lines_within_limit(self):
        cf = CommitFormat()
        message = "Short header\n\nShort body line."
        errors = cf.lines_length("abc123", message, 72)
        assert errors == 0

    def test_line_exceeds_limit(self):
        cf = CommitFormat()
        message = "fix: bug\n\n" + "a" * 80
        errors = cf.lines_length("abc123", message, 72)
        assert errors == Error.LINE_LENGTH

    def test_limit_disabled(self):
        cf = CommitFormat()
        message = "a" * 200
        errors = cf.lines_length("abc123", message, 0)
        assert errors == 0

    def test_url_line_allowed(self):
        cf = CommitFormat()
        message = "fix: add reference\n\n[1] \
            https://example.com/very/long/path/to/resource/with/very/long/url"
        errors = cf.lines_length("abc123", message, 50)
        assert errors == 0

    def test_url_wrong_format(self):
        cf = CommitFormat()
        # URL line without proper [index] format
        message = (
            "fix: refs\n\nSee this very long line with url https://example.com/path"
        )
        errors = cf.lines_length("abc123", message, 50)
        assert errors & Error.URL_FORMAT


class TestTemplateCheck:
    @pytest.fixture
    def cf_with_template(self, tmp_path):
        cf = CommitFormat()
        template_file = tmp_path / ".commit-format"
        template_file.write_text("""[header]
pattern = "^(fix: |feat: |doc: |ci: ).+$"

[body]
required = true

[footer]
pattern = "^(Signed-off-by: |Refs: ).+$"
""")
        cf.load_template(str(template_file))
        return cf

    def test_valid_commit(self, cf_with_template):
        message = "fix: repair bug\n\nFixed the issue.\n\nSigned-off-by: Author"
        errors = cf_with_template.template_check("abc123", message)
        assert errors == 0

    def test_invalid_header_pattern(self, cf_with_template):
        message = "broken: wrong prefix\n\nBody.\n\nSigned-off-by: Author"
        errors = cf_with_template.template_check("abc123", message)
        assert errors & Error.HEADER_PATTERN_MISMATCH

    def test_missing_blank_line_after_header(self, cf_with_template):
        message = "fix: bug\nNo blank line here.\n\nSigned-off-by: Author"
        errors = cf_with_template.template_check("abc123", message)
        assert errors & Error.BODY_MISSING

    def test_empty_body(self, cf_with_template):
        message = "fix: bug\n\n\n\nSigned-off-by: Author"
        errors = cf_with_template.template_check("abc123", message)
        assert errors & Error.BODY_MISSING

    def test_missing_footer(self, cf_with_template):
        message = "fix: bug\n\nBody content here."
        errors = cf_with_template.template_check("abc123", message)
        assert errors & Error.FOOTER_PATTERN_MISMATCH

    def test_invalid_footer_pattern(self, cf_with_template):
        message = "fix: bug\n\nBody content.\n\nInvalid-footer: Author"
        errors = cf_with_template.template_check("abc123", message)
        assert errors & Error.FOOTER_PATTERN_MISMATCH

    def test_no_template_loaded(self):
        cf = CommitFormat()
        errors = cf.template_check("abc123", "any message")
        assert errors == 0


class TestLoadTemplate:
    def test_load_valid_template(self, tmp_path):
        cf = CommitFormat()
        template_file = tmp_path / ".commit-format"
        template_file.write_text('[header]\npattern = "^fix: .+$"\n')
        cf.load_template(str(template_file))
        assert cf.commit_template is not None
        assert cf.commit_template["header"]["pattern"] == "^fix: .+$"

    def test_load_unquoted_pattern_template(self, tmp_path):
        cf = CommitFormat()
        template_file = tmp_path / ".commit-format"
        template_file.write_text(
            "[header]\n"
            "pattern = ^(fix: |feat: |doc: |ci: ).+$\n\n"
            "[body]\n"
            "required = true\n\n"
            "[footer]\n"
            "pattern = ^(Signed-off-by: |Refs: ).+$\n"
        )

        cf.load_template(str(template_file))

        assert cf.commit_template is not None
        assert (
            cf.commit_template["header"]["pattern"] == "^(fix: |feat: |doc: |ci: ).+$"
        )
        assert cf.commit_template["footer"]["pattern"] == "^(Signed-off-by: |Refs: ).+$"

    def test_load_nonexistent_template(self, tmp_path):
        cf = CommitFormat()
        with pytest.raises(SystemExit) as exc_info:
            cf.load_template(str(tmp_path / "nonexistent"))
        assert exc_info.value.code == 2


class TestFindConfigFile:
    def test_find_in_current_dir(self, tmp_path, monkeypatch):
        config_file = tmp_path / ".commit-format"
        config_file.write_text("[header]\n")
        monkeypatch.chdir(tmp_path)
        result = find_config_file()
        assert result == ".commit-format"

    def test_find_toml_variant(self, tmp_path, monkeypatch):
        config_file = tmp_path / ".commit-format.toml"
        config_file.write_text("[header]\n")
        monkeypatch.chdir(tmp_path)
        result = find_config_file()
        assert result == ".commit-format.toml"

    def test_no_config_found(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Mock git to return failure (not in a git repo)
        monkeypatch.setattr(
            "subprocess.run",
            lambda *args, **kwargs: type(
                "Result", (), {"returncode": 1, "stdout": ""}
            )(),
        )
        result = find_config_file()
        assert result is None


class TestHighlightWordsInTxt:
    def test_highlight_single_word(self):
        cf = CommitFormat()
        result = cf.highlight_words_in_txt("hello world", ["world"])
        assert result == "hello \033[91mworld\033[0m"

    def test_highlight_multiple_words(self):
        cf = CommitFormat()
        result = cf.highlight_words_in_txt("foo bar baz", ["foo", "baz"])
        assert result == "\033[91mfoo\033[0m bar \033[91mbaz\033[0m"

    def test_no_words_to_highlight(self):
        cf = CommitFormat()
        result = cf.highlight_words_in_txt("hello world", [])
        assert result == "hello world"


class TestRemoveAnsiColorCodes:
    def test_remove_red(self):
        cf = CommitFormat()
        result = cf.remove_ansi_color_codes("\033[91mred text\033[0m")
        assert result == "red text"

    def test_no_codes(self):
        cf = CommitFormat()
        result = cf.remove_ansi_color_codes("plain text")
        assert result == "plain text"


class TestGetVersion:
    def test_returns_string(self):
        result = get_version()
        assert isinstance(result, str)
        assert len(result) > 0
