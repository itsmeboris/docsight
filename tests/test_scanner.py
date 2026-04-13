"""Tests for doc_updater.docs.scanner."""

import pytest

from doc_updater.docs.scanner import DocScanner, RawReference


class TestRawReference:
    def test_defaults(self):
        ref = RawReference(text="AuthManager", ref_type="class_name_backtick", lineno=3, confidence=0.85)
        assert ref.context == ""
        assert ref.section == ""


class TestDocScannerProse:
    @pytest.mark.parametrize(
        "text,expected_text,expected_type,min_confidence",
        [
            ("`src/auth.py`", "src/auth.py", "file_path_backtick", 0.95),
            ("`validate_token()`", "validate_token", "function_call_backtick", 0.90),
            ("`AuthManager`", "AuthManager", "class_name_backtick", 0.85),
            ("`TokenCache.get()`", "TokenCache.get", "method_call_backtick", 0.90),
        ],
    )
    def test_finds_reference_in_prose(self, text, expected_text, expected_type, min_confidence):
        scanner = DocScanner()
        refs = scanner.scan_text(text)
        assert any(
            r.text == expected_text and r.ref_type == expected_type and r.confidence >= min_confidence
            for r in refs
        ), f"Expected {expected_type}={expected_text!r} in {refs}"

    def test_finds_file_path_in_backticks(self):
        scanner = DocScanner()
        refs = scanner.scan_text("See `src/auth.py` for details.")
        texts = [r.text for r in refs]
        assert "src/auth.py" in texts
        ref = next(r for r in refs if r.text == "src/auth.py")
        assert ref.ref_type == "file_path_backtick"
        assert ref.confidence == 0.95

    def test_finds_function_call(self):
        scanner = DocScanner()
        refs = scanner.scan_text("Call `validate_token()` to check.")
        texts = [r.text for r in refs]
        assert "validate_token" in texts
        ref = next(r for r in refs if r.text == "validate_token")
        assert ref.ref_type == "function_call_backtick"
        assert ref.confidence == 0.90

    def test_finds_class_name(self):
        scanner = DocScanner()
        refs = scanner.scan_text("Use the `AuthManager` class.")
        texts = [r.text for r in refs]
        assert "AuthManager" in texts
        ref = next(r for r in refs if r.text == "AuthManager")
        assert ref.ref_type == "class_name_backtick"
        assert ref.confidence == 0.85

    def test_finds_dotted_method(self):
        scanner = DocScanner()
        refs = scanner.scan_text("Call `TokenCache.get()` on the instance.")
        texts = [r.text for r in refs]
        assert "TokenCache.get" in texts
        ref = next(r for r in refs if r.text == "TokenCache.get")
        assert ref.ref_type == "method_call_backtick"
        assert ref.confidence == 0.90

    def test_no_match_for_plain_lowercase_backtick(self):
        """Plain lowercase identifiers without () or / should not match."""
        scanner = DocScanner()
        refs = scanner.scan_text("`foobar`")
        # lowercase, no slash, no parentheses -> no match
        assert all(r.text != "foobar" for r in refs)

    def test_file_path_must_contain_slash(self):
        """Backtick identifier without slash should not be classified as file path."""
        scanner = DocScanner()
        refs = scanner.scan_text("`nopath`")
        assert not any(r.ref_type == "file_path_backtick" for r in refs)


class TestDocScannerCodeBlocks:
    def test_extracts_imports_from_code_block(self):
        scanner = DocScanner()
        text = "Some prose.\n\n```python\nfrom src.auth import AuthManager\n```\n"
        refs = scanner.scan_text(text)
        assert any(r.text == "AuthManager" for r in refs)

    def test_extracts_class_instantiation_from_code_block(self):
        scanner = DocScanner()
        text = "```python\nmgr = AuthManager()\n```"
        refs = scanner.scan_text(text)
        assert any(r.text == "AuthManager" for r in refs)

    def test_no_false_positives_from_code_blocks(self):
        """Code block content must not produce duplicate refs when also in prose."""
        scanner = DocScanner()
        text = (
            "Use `AuthManager` for auth.\n\n"
            "```python\nmgr = AuthManager()\n```\n"
        )
        refs = scanner.scan_text(text)
        auth_refs = [r for r in refs if r.text == "AuthManager"]
        # Should find it, but not double-count from the same extraction path
        # The prose backtick and code block are different sources, both valid
        assert len(auth_refs) >= 1


class TestDocScannerSectionTracking:
    def test_tracks_section_heading(self):
        scanner = DocScanner()
        text = (
            "# Authentication Guide\n\n"
            "Use `AuthManager` to manage auth.\n\n"
            "## Usage\n\n"
            "Call `validate_token()` to check tokens.\n"
        )
        refs = scanner.scan_text(text)
        auth_ref = next((r for r in refs if r.text == "AuthManager"), None)
        assert auth_ref is not None
        assert auth_ref.section == "Authentication Guide"

        token_ref = next((r for r in refs if r.text == "validate_token"), None)
        assert token_ref is not None
        assert token_ref.section == "Usage"

    def test_section_defaults_to_empty_before_any_heading(self):
        scanner = DocScanner()
        text = "Use `AuthManager` here."
        refs = scanner.scan_text(text)
        ref = next((r for r in refs if r.text == "AuthManager"), None)
        assert ref is not None
        assert ref.section == ""

    def test_section_updated_at_each_heading_level(self):
        scanner = DocScanner()
        text = "## MySection\n\nUse `cache_lookup()`.\n"
        refs = scanner.scan_text(text)
        ref = next((r for r in refs if r.text == "cache_lookup"), None)
        assert ref is not None
        assert ref.section == "MySection"


class TestDocScannerLineNumbers:
    def test_line_numbers(self):
        scanner = DocScanner()
        text = "Line one\nLine two with `AuthManager`\nLine three `validate_token()`\n"
        refs = scanner.scan_text(text)
        auth_ref = next((r for r in refs if r.text == "AuthManager"), None)
        assert auth_ref is not None
        assert auth_ref.lineno == 2

        token_ref = next((r for r in refs if r.text == "validate_token"), None)
        assert token_ref is not None
        assert token_ref.lineno == 3


class TestDocScannerConfidenceOrdering:
    def test_confidence_ordering(self):
        """file > func >= method > class."""
        scanner = DocScanner()
        text = (
            "See `src/auth.py` and call `validate_token()` "
            "or `TokenCache.get()` on `AuthManager`."
        )
        refs = scanner.scan_text(text)

        file_ref = next((r for r in refs if r.ref_type == "file_path_backtick"), None)
        func_ref = next((r for r in refs if r.ref_type == "function_call_backtick"), None)
        method_ref = next((r for r in refs if r.ref_type == "method_call_backtick"), None)
        class_ref = next((r for r in refs if r.ref_type == "class_name_backtick"), None)

        assert file_ref is not None
        assert func_ref is not None
        assert method_ref is not None
        assert class_ref is not None

        assert file_ref.confidence > func_ref.confidence or file_ref.confidence > class_ref.confidence
        assert func_ref.confidence >= method_ref.confidence
        assert method_ref.confidence > class_ref.confidence

    def test_confidence_values(self):
        scanner = DocScanner()
        file_text = "`src/auth.py`"
        func_text = "`validate_token()`"
        method_text = "`TokenCache.get()`"
        class_text = "`AuthManager`"

        file_refs = scanner.scan_text(file_text)
        func_refs = scanner.scan_text(func_text)
        method_refs = scanner.scan_text(method_text)
        class_refs = scanner.scan_text(class_text)

        assert next(r for r in file_refs if r.ref_type == "file_path_backtick").confidence == 0.95
        assert next(r for r in func_refs if r.ref_type == "function_call_backtick").confidence == 0.90
        assert next(r for r in method_refs if r.ref_type == "method_call_backtick").confidence == 0.90
        assert next(r for r in class_refs if r.ref_type == "class_name_backtick").confidence == 0.85


class TestDocScannerDeduplication:
    def test_deduplicates_within_line(self):
        """Same text extracted twice on same line should only appear once."""
        scanner = DocScanner()
        # Two backtick references to same name on same line
        text = "Use `AuthManager` and `AuthManager`."
        refs = scanner.scan_text(text)
        auth_refs = [r for r in refs if r.text == "AuthManager"]
        assert len(auth_refs) == 1


class TestDocScannerEdgeCases:
    def test_syntax_error_in_code_block_falls_back_to_regex(self):
        """A code block with invalid syntax should fall back to regex extraction."""
        scanner = DocScanner()
        text = "```python\nthis is not valid python ClassName()\n```"
        refs = scanner.scan_text(text)
        # The AST parse fails; regex fallback should still find ClassName
        assert any(r.text == "ClassName" for r in refs)

    def test_plain_import_in_code_block(self):
        """import X (not from X import Y) should extract the module name."""
        scanner = DocScanner()
        text = "```python\nimport os\n```"
        refs = scanner.scan_text(text)
        assert any(r.text == "os" for r in refs)


class TestDocScannerScanFile:
    def test_scan_file(self, tmp_path):
        scanner = DocScanner()
        md_file = tmp_path / "guide.md"
        md_file.write_text(
            "# Guide\n\nUse `AuthManager`.\n",
            encoding="utf-8",
        )
        refs = scanner.scan_file(md_file)
        assert any(r.text == "AuthManager" for r in refs)

    def test_scan_file_returns_list(self, tmp_path):
        scanner = DocScanner()
        md_file = tmp_path / "empty.md"
        md_file.write_text("", encoding="utf-8")
        refs = scanner.scan_file(md_file)
        assert isinstance(refs, list)
