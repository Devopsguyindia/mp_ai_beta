from app.showcase.url_build import resolve_artwork_fetch_url_candidates, resolve_picture_url


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


def test_resolve_picture_url_encodes_spaces():
    assert (
        resolve_picture_url(
            base_url="https://cdn.example.com",
            server_path="folder",
            picture="my art.jpg",
        )
        == "https://cdn.example.com/folder/my%20art.jpg"
    )


def test_resolve_strips_duplicate_hostname_segment_in_picture():
    """Some ERP rows store the S3 host as the first path segment under the CDN base."""
    assert (
        resolve_picture_url(
            base_url="https://masterpiece.s3.amazonaws.com",
            server_path=None,
            picture="masterpiece.s3.amazonaws.com/c13997ef-3a28-476d-a91e-0a3ea35428bc.JPG",
        )
        == "https://masterpiece.s3.amazonaws.com/c13997ef-3a28-476d-a91e-0a3ea35428bc.JPG"
    )


def test_resolve_strips_repeated_hostname_segments():
    assert (
        resolve_picture_url(
            base_url="https://masterpiece.s3.amazonaws.com",
            server_path=None,
            picture="masterpiece.s3.amazonaws.com/masterpiece.s3.amazonaws.com/file.jpg",
        )
        == "https://masterpiece.s3.amazonaws.com/file.jpg"
    )


def test_resolve_picture_absolute_url_passthrough():
    u = "https://other.cdn.example/pic.png"
    assert resolve_picture_url(base_url="https://masterpiece.s3.amazonaws.com", server_path=None, picture=u) == u


def test_resolve_strips_host_prefix_from_server_path():
    assert (
        resolve_picture_url(
            base_url="https://masterpiece.s3.amazonaws.com",
            server_path="masterpiece.s3.amazonaws.com/gallery",
            picture="x.jpg",
        )
        == "https://masterpiece.s3.amazonaws.com/gallery/x.jpg"
    )


def test_resolve_server_path_hostname_only_is_redundant_with_cdn_base():
    """When server_path is only the CDN hostname, it must not repeat under MP_ASSET_CDN_BASE."""
    assert (
        resolve_picture_url(
            base_url="https://masterpiece.s3.amazonaws.com",
            server_path="masterpiece.s3.amazonaws.com",
            picture="c13997ef-3a28-476d-a91e-0a3ea35428bc.JPG",
        )
        == "https://masterpiece.s3.amazonaws.com/c13997ef-3a28-476d-a91e-0a3ea35428bc.JPG"
    )


def test_resolve_artwork_fetch_url_candidates_prefix_then_root_when_server_path_is_host():
    """resolved_url is root-only; byte fetch tries prefixed S3 key first, then root."""
    assert resolve_artwork_fetch_url_candidates(
        base_url="https://masterpiece.s3.amazonaws.com",
        server_path="masterpiece.s3.amazonaws.com",
        picture="x.jpg",
    ) == [
        "https://masterpiece.s3.amazonaws.com/masterpiece.s3.amazonaws.com/x.jpg",
        "https://masterpiece.s3.amazonaws.com/x.jpg",
    ]
