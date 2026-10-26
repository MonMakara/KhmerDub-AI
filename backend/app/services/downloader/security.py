import ipaddress
import logging
import re
import socket
import threading
from contextlib import contextmanager
from typing import List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DownloaderSecurityError(Exception):
    """Base exception for security and SSRF violations in Video Downloader."""
    pass


class SSRFSecurityError(DownloaderSecurityError):
    """Raised when an attempt to access private, local, or reserved networks is detected."""
    pass


class UnsupportedSourceError(DownloaderSecurityError):
    """Raised when the submitted URL source or domain is not permitted."""
    pass


class InvalidURLError(DownloaderSecurityError):
    """Raised when the submitted URL is malformed or invalid."""
    pass


# Specific cloud metadata IP addresses and hostnames to block explicitly
BLOCKED_HOSTNAMES: Set[str] = {
    "localhost",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}

BLOCKED_HOSTNAME_SUFFIXES: Tuple[str, ...] = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home",
    ".corp",
    ".arpa",
)

# Supported platform domains
YOUTUBE_DOMAINS: Set[str] = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
}

TIKTOK_DOMAINS: Set[str] = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
}

DIRECT_MEDIA_EXTENSIONS: Set[str] = {
    ".mp4",
    ".mov",
    ".webm",
    ".m4a",
    ".mp3",
    ".wav",
    ".ogg",
    ".aac",
    ".flac",
}


def is_safe_ip(ip_str: str) -> bool:
    """Verify whether an IP address is a safe, publicly routable address.

    Rejects loopback, private, link-local, multicast, cloud metadata, carrier-grade NAT,
    and reserved address ranges.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    # Block IPv4 or IPv6 loopback
    if ip.is_loopback:
        return False

    # Block RFC 1918 private IPv4 and RFC 4193 unique-local IPv6
    if ip.is_private:
        return False

    # Block link-local addresses (e.g., 169.254.0.0/16, fe80::/10)
    if ip.is_link_local:
        return False

    # Block multicast and broadcast
    if ip.is_multicast:
        return False

    # Block reserved / unspecified (e.g., 0.0.0.0, 240.0.0.0/4)
    if ip.is_reserved or ip.is_unspecified:
        return False

    # Special check for cloud instance metadata IPv4 (169.254.169.254)
    if str(ip) in {"169.254.169.254", "169.254.169.250", "169.254.169.2"}:
        return False

    # Check for Carrier-Grade NAT (100.64.0.0/10)
    if isinstance(ip, ipaddress.IPv4Address):
        cgnat_network = ipaddress.ip_network("100.64.0.0/10")
        if ip in cgnat_network:
            return False

        # Benchmark / Documentation nets (198.18.0.0/15, 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24)
        doc_nets = [
            ipaddress.ip_network("198.18.0.0/15"),
            ipaddress.ip_network("192.0.2.0/24"),
            ipaddress.ip_network("198.51.100.0/24"),
            ipaddress.ip_network("203.0.113.0/24"),
        ]
        for net in doc_nets:
            if ip in net:
                return False

    # Check for IPv6 mapped IPv4 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return is_safe_ip(str(ip.ipv4_mapped))

    return True


def resolve_and_verify_hostname(hostname: str, port: int = 443) -> List[str]:
    """Resolve a hostname to all IP addresses and verify that EVERY resolved address is safe.

    Prevents DNS rebinding and multi-homed internal addresses.
    """
    clean_host = hostname.strip().lower().rstrip(".")
    if not clean_host:
        raise InvalidURLError("Hostname cannot be empty.")

    # Check blocked hostnames
    if clean_host in BLOCKED_HOSTNAMES:
        raise SSRFSecurityError(f"Access to blocked hostname '{clean_host}' is prohibited.")

    for suffix in BLOCKED_HOSTNAME_SUFFIXES:
        if clean_host.endswith(suffix):
            raise SSRFSecurityError(f"Access to local or internal domain '{clean_host}' is prohibited.")

    # If hostname is a raw IP address, verify directly
    try:
        ipaddress.ip_address(clean_host)
        if not is_safe_ip(clean_host):
            raise SSRFSecurityError(f"Access to private or reserved IP '{clean_host}' is prohibited.")
        return [clean_host]
    except ValueError:
        pass

    # Resolve hostname via socket.getaddrinfo
    try:
        addr_info = socket.getaddrinfo(clean_host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise InvalidURLError(f"Unable to resolve hostname '{clean_host}': {e}") from e
    except Exception as e:
        raise InvalidURLError(f"DNS resolution failure for '{clean_host}': {e}") from e

    resolved_ips: List[str] = []
    for family, socktype, proto, canonname, sockaddr in addr_info:
        ip = sockaddr[0]
        if ip not in resolved_ips:
            resolved_ips.append(ip)

    if not resolved_ips:
        raise InvalidURLError(f"No IP addresses resolved for hostname '{clean_host}'.")

    # Strictly verify that EVERY resolved address is a safe public IP
    for ip in resolved_ips:
        if not is_safe_ip(ip):
            logger.warning("SSRF blocked: '%s' resolved to forbidden IP '%s'", clean_host, ip)
            raise SSRFSecurityError(
                f"Security check failed: '{clean_host}' resolved to restricted or private network address '{ip}'."
            )

    return resolved_ips


def validate_and_classify_url(url_str: str) -> Tuple[str, str]:
    """Validate submitted URL against SSRF and platform policy rules.

    Returns:
        (normalized_url, platform_name) where platform_name is 'YouTube', 'TikTok', or 'Direct Media'.
    Raises:
        DownloaderSecurityError if the URL violates security rules.
    """
    if not url_str or not isinstance(url_str, str):
        raise InvalidURLError("URL must be a non-empty string.")

    cleaned_url = url_str.strip()
    parsed = urlparse(cleaned_url)

    # 1. Scheme Check
    if parsed.scheme.lower() not in {"http", "https"}:
        raise InvalidURLError(
            f"Unsupported protocol scheme '{parsed.scheme}'. Only HTTP and HTTPS sources are permitted."
        )

    # 2. Hostname Check
    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError("URL is missing a valid hostname.")

    clean_host = hostname.lower().rstrip(".")

    # Quick check for raw loopback/private/metadata IP in hostname before platform check
    try:
        ipaddress.ip_address(clean_host)
        if not is_safe_ip(clean_host):
            raise SSRFSecurityError(f"Access to private or reserved IP '{clean_host}' is prohibited.")
    except ValueError:
        pass

    # Quick check for blocked hostnames
    if clean_host in BLOCKED_HOSTNAMES:
        raise SSRFSecurityError(f"Access to blocked hostname '{clean_host}' is prohibited.")

    for suffix in BLOCKED_HOSTNAME_SUFFIXES:
        if clean_host.endswith(suffix):
            raise SSRFSecurityError(f"Access to local or internal domain '{clean_host}' is prohibited.")

    # 3. Platform Classification & Whitelist Check
    platform: Optional[str] = None

    # Check YouTube
    if clean_host in YOUTUBE_DOMAINS or any(clean_host.endswith("." + d) for d in YOUTUBE_DOMAINS):
        platform = "YouTube"
    # Check TikTok
    elif clean_host in TIKTOK_DOMAINS or any(clean_host.endswith("." + d) for d in TIKTOK_DOMAINS):
        platform = "TikTok"
    else:
        # Check if direct media URL
        path_lower = parsed.path.lower()
        if any(path_lower.endswith(ext) for ext in DIRECT_MEDIA_EXTENSIONS):
            platform = "Direct Media"
        else:
            # Check for YouTube shorts or watch query without standard extension
            if "youtube.com" in clean_host or "youtu.be" in clean_host:
                platform = "YouTube"
            elif "tiktok.com" in clean_host:
                platform = "TikTok"
            else:
                raise UnsupportedSourceError(
                    f"Domain '{clean_host}' is not a recognized video source. "
                    "KhmerDub AI supports YouTube, TikTok, and direct public media files (.mp4, .mov, .webm, .mp3, .wav)."
                )

    # 4. Resolve & Verify DNS (SSRF check)
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    resolve_and_verify_hostname(clean_host, port)

    # Normalize URL: preserve original structure but clean spaces
    normalized_url = parsed.geturl().strip()
    return normalized_url, platform


# Thread-local storage to scope the SafeConnectionGuard only to downloader operations
_thread_local = threading.local()
_orig_create_connection = socket.create_connection
_orig_getaddrinfo = socket.getaddrinfo
_orig_socket_connect = socket.socket.connect
_orig_thread_start = threading.Thread.start


def is_guard_active() -> bool:
    """Check if the SSRF security guard is active in the current thread context."""
    return getattr(_thread_local, "active_guard", False)


def _guarded_create_connection(address, *args, **kwargs):
    """Wrapped socket.create_connection that verifies destination IP is safe."""
    if is_guard_active():
        host, port = address[0], address[1]
        try:
            ipaddress.ip_address(host)
            if not is_safe_ip(host):
                raise SSRFSecurityError(f"Connection blocked: attempted connection to restricted IP '{host}'.")
        except ValueError:
            # It's a hostname, resolve and verify
            resolve_and_verify_hostname(host, port)
    return _orig_create_connection(address, *args, **kwargs)


def _guarded_socket_connect(self, address):
    """Wrapped socket.socket.connect to block direct connections to restricted IPs."""
    if is_guard_active():
        if isinstance(address, (list, tuple)) and len(address) >= 2:
            raw_ip = str(address[0])
            try:
                ip = ipaddress.ip_address(raw_ip)
                if not is_safe_ip(str(ip)):
                    raise SSRFSecurityError(f"Direct socket connection to restricted IP '{raw_ip}' is prohibited.")
            except ValueError:
                pass
    return _orig_socket_connect(self, address)


def _guarded_getaddrinfo(host, port, *args, **kwargs):
    """Wrapped socket.getaddrinfo that inspects hostnames and validates EVERY resolved IP.

    Completely neutralizes DNS rebinding, internal Docker subnets, and local address leaks.
    """
    if is_guard_active():
        if host:
            clean_host = str(host).strip().lower().rstrip(".")
            if clean_host in BLOCKED_HOSTNAMES:
                raise SSRFSecurityError(f"Access to blocked hostname '{clean_host}' is prohibited.")
            for suffix in BLOCKED_HOSTNAME_SUFFIXES:
                if clean_host.endswith(suffix):
                    raise SSRFSecurityError(f"Access to local or internal domain '{clean_host}' is prohibited.")
            try:
                ipaddress.ip_address(clean_host)
                if not is_safe_ip(clean_host):
                    raise SSRFSecurityError(f"Access to restricted or private IP '{clean_host}' is prohibited.")
            except ValueError:
                pass

        results = _orig_getaddrinfo(host, port, *args, **kwargs)
        for res in results:
            sockaddr = res[4]
            ip = sockaddr[0]
            if not is_safe_ip(ip):
                raise SSRFSecurityError(
                    f"Security check failed: host '{host}' resolved to restricted or private IP address '{ip}'."
                )
        return results

    return _orig_getaddrinfo(host, port, *args, **kwargs)


def _guarded_thread_start(self, *args, **kwargs):
    """Ensure child threads spawned from an active guard context inherit the SSRF guard."""
    if is_guard_active():
        orig_run = self.run

        def _wrapped_run(*r_args, **r_kwargs):
            _thread_local.active_guard = True
            try:
                return orig_run(*r_args, **r_kwargs)
            finally:
                _thread_local.active_guard = False

        self.run = _wrapped_run
    return _orig_thread_start(self, *args, **kwargs)


@contextmanager
def safe_connection_guard():
    """Context manager that activates connection-time SSRF guards in the current thread and child threads.

    Intercepts socket operations so that any DNS rebinding or redirect to private/internal IPs
    is rejected at connection time.
    """
    _thread_local.active_guard = True
    try:
        yield
    finally:
        _thread_local.active_guard = False


# Install global hooks once
socket.create_connection = _guarded_create_connection
socket.getaddrinfo = _guarded_getaddrinfo
socket.socket.connect = _guarded_socket_connect
threading.Thread.start = _guarded_thread_start
