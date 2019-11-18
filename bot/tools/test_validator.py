# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from .validator import validate


def test_top_struct():
    """Only a dict should be supoprted as top structure"""
    with pytest.raises(AssertionError, match="Top structure is not a dict"):
        validate([])
    with pytest.raises(AssertionError, match="Top structure is not a dict"):
        validate("xx")
    with pytest.raises(AssertionError, match="Top structure is not a dict"):
        validate(None)

    assert validate({})


def test_dict_struct():
    """The payload should only have string as keys and lists as values"""
    with pytest.raises(AssertionError, match="All top keys must be strings"):
        validate({1: []})
    with pytest.raises(AssertionError, match="All top keys must be strings"):
        validate({"1": [], 12: None})
    with pytest.raises(AssertionError, match="All top values must be lists"):
        validate({"A": [], "B": None})

    assert validate({"test": [], "test2": []})


def test_paths():
    """The top keys must be relative paths"""
    with pytest.raises(AssertionError, match="Path should not be absolute"):
        validate({"/a/b/c": [], "test.cpp": [1, 2]})

    assert validate({"a/b/c": [], "test.cpp": []})


def test_issues():
    """Test the structure of issues"""
    with pytest.raises(
        AssertionError, match="All issues for path/to/file.cpp must be dicts"
    ):
        assert validate({"path/to/file.cpp": [1, {}]})

    # Missing required keys
    with pytest.raises(
        Exception,
        match="Invalid issue n°1 for path/file.x : Missing required keys column, level, line, message",
    ):
        validate({"path/file.x": [{"path": "xx"}]})

    # Line is string instead of int
    with pytest.raises(
        Exception,
        match="Invalid issue n°1 for path/file.z : line must be either a positive integer or null",
    ):
        validate(
            {
                "path/file.z": [
                    {
                        "path": "xx",
                        "level": "",
                        "column": "",
                        "message": "",
                        "line": "123",
                    }
                ]
            }
        )

    # Column is string instead of int
    with pytest.raises(
        Exception,
        match="Invalid issue n°1 for path/file.z : column must be either a positive integer or null",
    ):
        validate(
            {
                "path/file.z": [
                    {
                        "path": "xx",
                        "level": "",
                        "column": "45",
                        "message": "",
                        "line": 123,
                    }
                ]
            }
        )

    # Invalid level
    with pytest.raises(
        Exception,
        match="Invalid issue n°1 for path/file.z : level must be in warning, error",
    ):
        validate(
            {
                "path/file.z": [
                    {
                        "path": "xx",
                        "level": "test",
                        "column": 45,
                        "message": "",
                        "line": 123,
                    }
                ]
            }
        )

    # Message must be non-enpty
    with pytest.raises(
        Exception,
        match="Invalid issue n°1 for path/file.z : message must be a non-empty string",
    ):
        validate(
            {
                "path/file.z": [
                    {
                        "path": "xx",
                        "level": "error",
                        "column": 45,
                        "message": "",
                        "line": 123,
                    }
                ]
            }
        )

    # Invalid path
    with pytest.raises(
        Exception,
        match=r"Invalid issue n°1 for path/file.z : Top path and issue path must be identical \(path/file.z != xx\)",
    ):
        validate(
            {
                "path/file.z": [
                    {
                        "path": "xx",
                        "level": "error",
                        "column": 45,
                        "message": "some error happened",
                        "line": 123,
                    }
                ]
            }
        )

    # Valid minimal issue
    assert validate(
        {
            "path/file.z": [
                {
                    "path": "path/file.z",
                    "level": "error",
                    "column": 45,
                    "message": "some error happened",
                    "line": 123,
                }
            ]
        }
    )
