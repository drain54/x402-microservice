import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple

def is_safe_url(target_url: str) -> Tuple[bool, str]:
    """
    SSRF Protection Gate for AI Agent Micro-services.
    Validates URL scheme (http/https only) and ensures target host does not resolve
    to loopback, private RFC 1918, link-local, multicast, or reserved networks.
    """
    try:
        parsed = urlparse(target_url)
    except Exception as e:
        return False, f"Invalid URL structure: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported scheme '{parsed.scheme}'. Only http and https are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must include a valid hostname."

    # Prevent loopback aliases
    if hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False, "Access to localhost/loopback addresses is forbidden."

    try:
        # Resolve all DNS A and AAAA records for the host
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False, f"Failed to resolve DNS for hostname '{hostname}'"
    except Exception as e:
        return False, f"DNS resolution error: {e}"

    for item in addr_info:
        ip_str = item[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            ):
                return False, f"Target IP {ip_str} falls within restricted/private address space."
        except ValueError:
            return False, f"Invalid IP address returned: {ip_str}"

    return True, ""
