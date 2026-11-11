"""Canonical JSON (RFC 8785 subset) tests — vectors derived from the RFC examples."""

import pytest

from evidence.canonical import CanonicalizationError, canonical_json, canonicalize, sha256_hex


class TestSorting:
    def test_keys_sorted_by_code_unit(self):
        assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'

    def test_insertion_order_irrelevant(self):
        assert canonical_json({"x": 1, "a": 2}) == canonical_json({"a": 2, "x": 1})

    def test_prefix_orders_before_longer_key(self):
        assert canonical_json({"ab": 1, "b": 2, "a": 3}) == '{"a":3,"ab":1,"b":2}'

    def test_astral_sorts_before_high_bmp_despite_larger_code_point(self):
        # RFC 8785 §3.2.3: U+1F600 encodes as a surrogate pair whose first
        # code unit (D83D) is smaller than U+FB33, so the emoji sorts BEFORE
        # the Hebrew letter even though its code point is larger — UTF-16
        # code-unit ordering, not code-point ordering.
        value = {"\U0001f600": 1, "\ufb33": 2, "\u20ac": 3, "1": 4, '"': 5, "\r": 6}
        expected = '{"\\r":6,"\\"":5,"1":4,"\u20ac":3,"\U0001f600":1,"\ufb33":2}'
        assert canonical_json(value) == expected

    def test_nested_objects_sorted_at_every_level(self):
        value = {"z": {"b": [1, {"y": 1, "a": 2}]}, "a": 3}
        assert canonical_json(value) == '{"a":3,"z":{"b":[1,{"a":2,"y":1}]}}'


class TestEscaping:
    def test_shorthand_escapes(self):
        assert canonical_json({"k": "a\tb\nc\rd\be\ff"}) == '{"k":"a\\tb\\nc\\rd\\be\\ff"}'

    def test_quote_and_backslash_escaped(self):
        assert canonical_json({"k": 'say "hi" \\ done'}) == '{"k":"say \\"hi\\" \\\\ done"}'

    def test_other_control_chars_use_lowercase_hex(self):
        assert canonical_json({"k": "\x00\x01\x1f"}) == '{"k":"\\u0000\\u0001\\u001f"}'

    def test_non_ascii_output_raw(self):
        assert canonical_json({"k": "ሴ pile 💩"}) == '{"k":"ሴ pile 💩"}'

    def test_line_separator_not_escaped(self):
        # RFC 8785 only escapes control characters; U+2028 stays raw.
        sep = chr(0x2028)
        assert canonical_json({"k": f"a{sep}b"}) == '{"k":"a' + sep + 'b"}'

    def test_lone_surrogate_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"k": "bad \ud800 surrogate"})

    def test_lone_surrogate_key_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"bad \udfff": 1})


class TestNumbers:
    def test_safe_integers_round_trip(self):
        assert canonical_json({"max": 9007199254740991, "min": -9007199254740991, "zero": 0}) == (
            '{"max":9007199254740991,"min":-9007199254740991,"zero":0}'
        )

    def test_integer_above_safe_range_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"k": 9007199254740992})

    def test_integer_below_safe_range_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"k": -9007199254740992})

    def test_float_rejected(self):
        with pytest.raises(CanonicalizationError, match="floats are not representable"):
            canonical_json({"k": 1.5})

    def test_nested_float_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"outer": {"inner": [1, 2.5]}})


class TestTypes:
    def test_null_bool(self):
        assert canonical_json({"a": None, "b": True, "c": False}) == '{"a":null,"b":true,"c":false}'

    def test_bool_is_not_serialized_as_int(self):
        assert canonical_json({"t": True, "n": 1}) == '{"n":1,"t":true}'

    def test_empty_containers(self):
        assert canonical_json({"list": [], "obj": {}}) == '{"list":[],"obj":{}}'

    def test_tuples_accepted(self):
        assert canonical_json((1, "a")) == '[1,"a"]'

    def test_sets_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({1, 2})

    def test_non_string_keys_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({1: "a"})

    def test_bytes_rejected(self):
        with pytest.raises(CanonicalizationError):
            canonical_json({"k": b"raw"})


class TestEncoding:
    def test_canonicalize_is_utf8_of_canonical_json(self):
        value = {"k": "valeu→r 💶", "n": 5}
        assert canonicalize(value) == canonical_json(value).encode("utf-8")

    def test_round_trip_through_json_module(self):
        import json

        value = {"b": [1, {"deep": "τext"}], "a": None}
        text = canonical_json(value)
        assert json.loads(text) == value


def test_sha256_hex_known_vector():
    assert sha256_hex(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
