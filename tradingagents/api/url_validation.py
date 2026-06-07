from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeBackendUrl(ValueError):
    pass


def _is_private_address(raw: str) -> bool:
    address = ipaddress.ip_address(raw.split("%", 1)[0])
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_backend_url(url: str | None, *, allow_private: bool) -> str | None:
    if url is None:
        return None

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeBackendUrl("backend_url must start with http:// or https://")
    if not parsed.hostname:
        raise UnsafeBackendUrl("backend_url must include a host")
    if allow_private:
        return url

    host = parsed.hostname
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeBackendUrl("backend_url port is invalid") from exc

    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise UnsafeBackendUrl(f"backend_url host cannot be resolved: {host}") from exc

    for raw_address in addresses:
        if _is_private_address(raw_address):
            raise UnsafeBackendUrl(
                "private backend URLs are disabled; set "
                "TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS=true for trusted local deployments"
            )

    return url
