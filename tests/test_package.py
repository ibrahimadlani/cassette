import cassette


def test_package_exposes_a_version() -> None:
    assert cassette.__version__.count(".") == 2
