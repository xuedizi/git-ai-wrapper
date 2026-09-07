#!/usr/bin/env python3
"""Validate publisher-owned JSON and embed it in the patched sidecar. Never log values."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, maximum):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def validate(config, version):
    require(isinstance(config, dict), 'configuration must be an object')
    require(set(config) <= {'enabled', 'organization_id', 'identity_secret', 'destinations',
                           'max_bytes', 'commit_reserved_bytes', 'retention_secs'}, 'unknown configuration field')
    require(type(config.get('enabled')) is bool, 'enabled must be a boolean')
    if not config['enabled']:
        return
    require(bool(re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+-tac\.v[0-9]+\.[0-9]+\.[0-9]+', version)),
            'enabled configuration requires an exact wrapper release version')
    require(text(config.get('organization_id'), 256), 'organization_id is required')
    secret = config.get('identity_secret')
    require(text(secret, 1024) and len(secret.encode()) >= 32, 'identity_secret must contain at least 32 bytes')
    maximum = config.get('max_bytes', 104857600)
    reserved = config.get('commit_reserved_bytes', 20971520)
    retention = config.get('retention_secs', 2592000)
    require(type(maximum) is int and type(reserved) is int and 0 <= reserved < maximum <= 2**63-1,
            'invalid queue capacity')
    require(type(retention) is int and 60 <= retention <= 365*86400, 'invalid retention')
    destinations = config.get('destinations')
    require(isinstance(destinations, list) and 1 <= len(destinations) <= 8, 'invalid destinations')
    ids = set()
    for dest in destinations:
        require(isinstance(dest, dict), 'destination must be an object')
        require(set(dest) <= {'id', 'endpoint', 'token', 'ack', 'event_types', 'min_interval_ms', 'adapter'},
                'unknown destination field')
        require(text(dest.get('id'), 128) and dest['id'] not in ids, 'invalid or duplicate destination ID')
        ids.add(dest['id'])
        require(text(dest.get('endpoint'), 2048), 'endpoint is required')
        url = urlsplit(dest['endpoint'])
        require(url.scheme == 'https' and url.hostname and not url.username and not url.password
                and not url.query and not url.fragment, 'endpoint must be HTTPS without credentials/query/fragment')
        require(text(dest.get('token'), 8192) and '\r' not in dest['token'] and '\n' not in dest['token'],
                'valid token is required')
        require(dest.get('adapter', 'autopai-v1') == 'autopai-v1', 'unsupported adapter')
        types = dest.get('event_types')
        require(isinstance(types, list) and bool(types) and all(t in ('checkpoint', 'commit') for t in types),
                'event_types must select checkpoint and/or commit')
        interval = dest.get('min_interval_ms', 500)
        require(type(interval) is int and 100 <= interval <= 60000, 'invalid request interval')
        ack = dest.get('ack', {'mode':'unconfirmed'})
        require(isinstance(ack, dict) and ack.get('mode') in ('unconfirmed', 'http_200', 'json'), 'invalid ACK mode')
        if ack['mode'] == 'json':
            require(set(ack) <= {'mode', 'pointer', 'equals', 'event_id_pointer'} and 'equals' in ack,
                    'invalid JSON ACK fields')
            require(isinstance(ack.get('pointer'), str) and ack['pointer'].startswith('/'), 'invalid ACK pointer')
            pointer = ack.get('event_id_pointer')
            require(pointer is None or isinstance(pointer, str) and pointer.startswith('/'), 'invalid event ID pointer')
        else:
            require(set(ack) == {'mode'}, 'unexpected ACK fields')


def rust_string(value):
    hashes = '#'
    while '"' + hashes in value:
        hashes += '#'
    return 'r' + hashes + '"' + value + '"' + hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--version', default='development')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        cfg = json.loads(args.config.read_text()) if args.config else {'enabled':False}
        validate(cfg, args.version)
        # A disabled build must not accidentally include unused production secrets.
        if not cfg['enabled']:
            cfg = {'enabled':False}
        data = json.dumps(cfg, ensure_ascii=False, separators=(',', ':'))
        args.out.write_text('// Generated from publisher configuration; do not commit generated secrets.\n'
                            + 'pub const CONFIG: &str = ' + rust_string(data) + ';\n'
                            + 'pub const WRAPPER_VERSION: &str = ' + rust_string(args.version) + ';\n')
        args.out.chmod(0o600)
    except (ValueError, OSError, TypeError):
        print('enterprise build configuration is invalid or unreadable; check publisher fields and version', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
