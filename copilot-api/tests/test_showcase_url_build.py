from app.showcase.url_build import resolve_picture_url


def test_resolve_picture_url_joins_paths():
    assert (
        resolve_picture_url(
            base_url="https://cdn.example.com/",
            server_path="/a/b",
            picture="file.jpg",
        )
        == "https://cdn.example.com/a/b/file.jpg"
    )


def test_resolve_picture_url_no_double_slash():
    assert (
        resolve_picture_url(
            base_url="https://cdn.example.com",
            server_path="prefix/",
            picture="pic.png",
        )
        == "https://cdn.example.com/prefix/pic.png"
    )


def test_resolve_empty_picture():
    assert resolve_picture_url(base_url="https://x.com", server_path=None, picture="") == ""
