from engineering_office.cli import build_parser


def test_ui_command_has_user_friendly_launch_options():
    args = build_parser().parse_args(["ui", ".", "--port", "8123", "--no-open", "--app"])
    assert args.command == "ui"
    assert args.port == 8123
    assert args.no_open is True
    assert args.app is True


def test_ui_cli_rejects_non_loopback_bind_host():
    import pytest
    from engineering_office.cli import _validate_ui_host

    assert _validate_ui_host("127.0.0.1") == "127.0.0.1"
    assert _validate_ui_host("localhost") == "localhost"
    assert _validate_ui_host("::1") == "::1"
    with pytest.raises(ValueError, match="loopback"):
        _validate_ui_host("0.0.0.0")
    with pytest.raises(ValueError, match="loopback"):
        _validate_ui_host("192.168.1.25")
