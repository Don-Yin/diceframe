# -*- coding: utf-8 -*-
"""Web Transport：HTTP / HTTPS 的唯一归属地。

业务层（游戏、规则、AI、房间、插件）不得 import 本包；
本包也不得 import Web 层或任何业务模块（由架构边界测试守护）。
"""

from src.web_transport.certificates.acme import (
    AcmeCertificateProvider,
    AcmeIdentifier as AcmeOrderIdentifier,
    AcmeIssueRequest,
    AcmeIssueResult,
)
from src.web_transport.certificates.acme_client import AcmeClient, AcmeError
from src.web_transport.certificates.base import CertificateError, CertificateProvider, PreparedCertificate
from src.web_transport.certificates.metadata import CertificateMetadata
from src.web_transport.certificates.self_signed import SelfSignedCertificateProvider
from src.web_transport.certificates.storage import CertificateStore
from src.web_transport.config import (
    IDENTIFIER_TYPE_DNS,
    IDENTIFIER_TYPE_IP,
    IP_CERTIFICATE_PROFILE,
    TLS_MODE_LETS_ENCRYPT,
    TLS_MODE_OFF,
    TLS_MODE_SELF_SIGNED,
    AcmeSettings,
    WebTransportConfig,
    parse_web_transport,
    validate_activation,
    web_transport_config_from_state,
)
from src.web_transport.endpoint import ServerEndpoint
from src.web_transport.transport import ServerTransport, build_server_transport

__all__ = [
    "AcmeCertificateProvider",
    "AcmeClient",
    "AcmeError",
    "AcmeIssueRequest",
    "AcmeIssueResult",
    "AcmeOrderIdentifier",
    "AcmeSettings",
    "IDENTIFIER_TYPE_DNS",
    "IDENTIFIER_TYPE_IP",
    "IP_CERTIFICATE_PROFILE",
    "CertificateError",
    "CertificateMetadata",
    "CertificateProvider",
    "CertificateStore",
    "PreparedCertificate",
    "SelfSignedCertificateProvider",
    "ServerEndpoint",
    "ServerTransport",
    "TLS_MODE_LETS_ENCRYPT",
    "TLS_MODE_OFF",
    "TLS_MODE_SELF_SIGNED",
    "WebTransportConfig",
    "build_server_transport",
    "parse_web_transport",
    "validate_activation",
    "web_transport_config_from_state",
]
