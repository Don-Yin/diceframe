"""Web Transport 配置解析、兼容与脱敏契约。"""

from __future__ import annotations

from src.web_transport.config import (
    TLS_MODE_LETS_ENCRYPT,
    TLS_MODE_OFF,
    TLS_MODE_SELF_SIGNED,
    parse_web_transport,
    validate_activation,
)


def test_missing_field_defaults_to_off():
    config = parse_web_transport({})
    assert config.tls_mode == TLS_MODE_OFF
    assert config.scheme == "http"
    assert config.tls_mode_source == "default"


def test_none_saved_config_is_off():
    config = parse_web_transport(None, {})
    assert config.tls_mode == TLS_MODE_OFF


def test_all_public_modes_parse():
    assert parse_web_transport({"tls_mode": "off"}).tls_mode == "off"
    assert parse_web_transport({"tls_mode": "self_signed"}).tls_mode == "self_signed"
    assert parse_web_transport({"tls_mode": "lets_encrypt"}).tls_mode == "lets_encrypt"
    assert parse_web_transport({"tls_mode": "SELF_SIGNED"}).scheme == "https"


def test_invalid_mode_falls_back_to_off():
    config = parse_web_transport({"tls_mode": "turbo_tls"})
    assert config.tls_mode == TLS_MODE_OFF
    # lets_encrypt 之外的无效值同样不可激活。
    assert validate_activation(config) is None or "不支持" in validate_activation(config)


def test_env_overrides_saved_config():
    config = parse_web_transport(
        {"tls_mode": "off"},
        {"TRPG_TLS_MODE": "self_signed"},
    )
    assert config.tls_mode == TLS_MODE_SELF_SIGNED
    assert config.tls_mode_source == "env"


def test_invalid_env_mode_is_ignored():
    config = parse_web_transport(
        {"tls_mode": "self_signed"},
        {"TRPG_TLS_MODE": "not-a-mode"},
    )
    assert config.tls_mode == TLS_MODE_SELF_SIGNED
    assert config.tls_mode_source == "config"


def test_unknown_fields_are_ignored_for_rollback_safety():
    config = parse_web_transport(
        {"tls_mode": "off", "future_option": {"nested": True}, "tls_strangeness": 1},
        {},
    )
    assert config.tls_mode == TLS_MODE_OFF


def test_reserved_fields_are_reported_not_silently_applied():
    config = parse_web_transport(
        {"tls_mode": "off", "cert_file": "C:/some.pem", "key_file": "C:/some.key"},
        {},
    )
    assert config.cert_file and config.key_file
    assert "web_transport.cert_file" in config.reserved_rejects
    error = validate_activation(config)
    assert error and "暂不支持" in error


def test_acme_settings_are_parsed_and_canonicalized():
    config = parse_web_transport(
        {
            "tls_mode": "lets_encrypt",
            "acme": {
                "identifier_type": "dns",
                "identifier": "Game.Example.COM.",
                "contact_email": "admin@example.com",
                "challenge_type": "http-01",
                "directory": "production",
            },
        },
        {},
    )
    # canonical 小写、去尾点；不保存翻译显示名。
    assert config.acme.identifier == "game.example.com"
    assert config.acme.identifier_type == "dns"
    assert config.acme.contact_email == "admin@example.com"
    assert config.acme.challenge_type == "http-01"
    assert config.acme.directory == "production"
    assert config.acme.http_challenge_port == 80
    # 域名模式不强制 shortlived profile。
    assert config.acme.certificate_profile == ""
    assert validate_activation(config) is None


def test_ip_mode_forces_shortlived_profile_and_rejects_private_addresses():
    public = parse_web_transport(
        {
            "tls_mode": "lets_encrypt",
            "acme": {"identifier_type": "ip", "identifier": "2606:4700:4700::1111"},
        },
        {},
    )
    assert public.acme.identifier == "2606:4700:4700::1111"
    # CA 要求：公网 IP 证书必须使用短期 profile。
    assert public.acme.certificate_profile == "shortlived"
    assert validate_activation(public) is None

    for reserved in ("127.0.0.1", "192.168.1.5", "10.0.0.1", "172.16.0.1", "fe80::1", "::1"):
        config = parse_web_transport(
            {
                "tls_mode": "lets_encrypt",
                "acme": {"identifier_type": "ip", "identifier": reserved},
            },
            {},
        )
        error = validate_activation(config)
        assert error and "公网" in error, reserved


def test_invalid_acme_fields_are_rejected_with_actionable_errors():
    config = parse_web_transport(
        {
            "tls_mode": "lets_encrypt",
            "acme": {
                "identifier_type": "dns",
                "identifier": "localhost",
                "challenge_type": "dns-01",
                "directory": "prod",
            },
        },
        {},
    )
    error = validate_activation(config)
    assert error and "Let's Encrypt 配置无效" in error


def test_lets_encrypt_without_identifier_is_rejected():
    config = parse_web_transport({"tls_mode": "lets_encrypt"}, {})
    error = validate_activation(config)
    assert error and "Let's Encrypt 配置无效" in error


def test_acme_env_overrides_saved_config():
    config = parse_web_transport(
        {"tls_mode": "lets_encrypt", "acme": {"identifier": "old.example.com"}},
        {
            "TRPG_TLS_MODE": "lets_encrypt",
            "TRPG_TLS_IDENTIFIER_TYPE": "ip",
            "TRPG_TLS_IDENTIFIER": "2606:4700:4700::1112",
            "TRPG_TLS_CONTACT_EMAIL": "a@b.com",
        },
    )
    assert config.tls_mode_source == "env"
    assert config.acme.identifier_type == "ip"
    assert config.acme.identifier == "2606:4700:4700::1112"
    assert config.acme.contact_email == "a@b.com"
    assert config.acme.certificate_profile == "shortlived"


def test_lets_encrypt_activation_is_valid_when_configured():
    config = parse_web_transport(
        {
            "tls_mode": "lets_encrypt",
            "acme": {"identifier_type": "dns", "identifier": "game.example.com"},
        },
        {},
    )
    assert validate_activation(config) is None
    view = config.redacted_view()
    assert view["lets_encrypt_available"] is True
    assert view["acme"]["identifier"] == "game.example.com"


def test_redacted_view_contains_no_key_material():
    config = parse_web_transport(
        {"tls_mode": "self_signed", "cert_file": "C:/secret.pem", "key_file": "C:/secret.key"},
        {},
    )
    view = config.redacted_view()
    text = repr(view)
    assert "secret" not in text
    assert "cert_file" not in text
    assert "key_file" not in text
    assert view["tls_mode"] == "self_signed"
    assert view["scheme"] == "https"
