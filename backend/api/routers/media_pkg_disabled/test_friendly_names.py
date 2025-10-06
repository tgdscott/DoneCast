import pytest
from .write import parse_friendly_names

def test_json_list():
    assert parse_friendly_names('["A","B"]') == ["A", "B"]
    assert parse_friendly_names('[1,2]') == ["1", "2"]

def test_json_string():
    assert parse_friendly_names('"A"') == ["A"]
    assert parse_friendly_names('123') == ["123"]

def test_powershell_quoted():
    assert parse_friendly_names("'A','B'") == ["A", "B"]
    assert parse_friendly_names('"A","B"') == ["A", "B"]

def test_csv_fallback():
    assert parse_friendly_names('A,B,C') == ["A", "B", "C"]
    assert parse_friendly_names(' A , B , , C ') == ["A", "B", "C"]
    assert parse_friendly_names('[A,B]') == ["A", "B"]
    assert parse_friendly_names('') == []
    assert parse_friendly_names(None) == []
