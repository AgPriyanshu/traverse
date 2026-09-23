from api.extraction.normalization import (
    nickname_key,
    normalize,
    strip_honorifics,
    token_set_key,
)


class TestNormalize:
    def test_folds_case_punctuation_and_whitespace(self) -> None:
        assert normalize("Mr.  Darcy") == "mr darcy"
        assert normalize("Elizabeth,") == "elizabeth"
        assert normalize("  Bennet  ") == "bennet"


class TestStripHonorifics:
    def test_strips_a_leading_title(self) -> None:
        assert strip_honorifics("Mr. Darcy") == "darcy"
        assert strip_honorifics("Miss Elizabeth Bennet") == "elizabeth bennet"
        assert strip_honorifics("Dr. Watson") == "watson"

    def test_strips_a_hyphenated_suffix(self) -> None:
        assert strip_honorifics("Kazu-san") == "kazu"
        assert strip_honorifics("Tokita-sama") == "tokita"

    def test_leaves_a_plain_name_untouched(self) -> None:
        assert strip_honorifics("Elizabeth Bennet") == "elizabeth bennet"


class TestTokenSetKey:
    def test_is_order_independent(self) -> None:
        assert token_set_key("Tokita Kazu") == token_set_key("Kazu Tokita")

    def test_ignores_honorifics(self) -> None:
        assert token_set_key("Mr. Darcy") == token_set_key("Darcy")

    def test_distinguishes_different_names(self) -> None:
        assert token_set_key("Catherine Earnshaw") != token_set_key("Catherine Linton")


class TestNicknameKey:
    def test_folds_a_known_diminutive(self) -> None:
        assert nickname_key("Lizzy Bennet") == nickname_key("Elizabeth Bennet")
        assert nickname_key("Eliza") == nickname_key("Elizabeth")

    def test_does_not_fold_the_surname(self) -> None:
        assert nickname_key("Lizzy Bennet") != nickname_key("Lizzy Darcy")

    def test_unknown_first_token_is_unchanged(self) -> None:
        assert nickname_key("Fitzwilliam Darcy") == "fitzwilliam darcy"
