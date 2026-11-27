from documents.services.text_clean import clean_embedded_text


def test_nfkc_repairs_ligatures():
    assert clean_embedded_text("Certiﬁcate") == "Certificate"


def test_whitespace_is_collapsed_per_line():
    assert clean_embedded_text("hello   world\t\tagain") == "hello world again"


def test_empty_lines_are_dropped():
    assert clean_embedded_text("one\n\n\n two \n") == "one\ntwo"


def test_control_characters_are_removed():
    assert clean_embedded_text("a\x00b\x07c") == "abc"


def test_clean_text_passes_through():
    text = "This is to certify that\nJane Doe passed."
    assert clean_embedded_text(text) == text


def test_empty_input():
    assert clean_embedded_text("") == ""
