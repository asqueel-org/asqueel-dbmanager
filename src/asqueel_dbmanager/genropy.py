"""Optional, configuration-only Genropy integration for the local CLI."""

import os
from urllib.parse import unquote, urlsplit

from asqueel_dbmanager import operations


class GenropyConnectionError(RuntimeError):
    """A safe diagnostic that never contains configuration values."""


def _instance_config(instance):
    try:
        try:
            from gnr.app.pathresolver import PathResolver
        except ModuleNotFoundError as error:
            if error.name != 'gnr.app.pathresolver':
                raise
            from gnr.app.gnrdeploy import PathResolver
    except ImportError:
        raise GenropyConnectionError(
            'Genropy and its dependencies must be installed in this Python environment to use -g'
        ) from None
    try:
        return PathResolver().get_instanceconfig(instance)
    except Exception:
        raise GenropyConnectionError(
            'Cannot resolve the Genropy instance; check its name and Genropy configuration'
        ) from None


def _value(value):
    if isinstance(value, str):
        # Genropy supports XML environment templates and $VARIABLE DB attributes.
        value = value.format_map(os.environ)
        if value.startswith('$'):
            value = os.environ[value[1:]]
    return value


def connection_from_instance(instance):
    """Resolve the primary PostgreSQL connection without constructing GnrApp."""
    if not instance or any(char in instance for char in ':/*\\'):
        raise GenropyConnectionError('Use a plain Genropy instance name; remote/store selectors are unsupported')
    config = _instance_config(instance)
    try:
        attrs = dict(config.getAttr('db') or {})
        keys = ('implementation', 'host', 'port', 'user', 'password', 'dbname',
                'sslmode', 'connect_timeout')
        attrs = {key: _value(attrs[key]) for key in keys if key in attrs}
        if dsn := os.environ.get('GNR_DB_DSN'):
            parsed = urlsplit(dsn)
            if parsed.query or parsed.fragment:
                raise ValueError('Unsupported DSN options')
            attrs.update(implementation=parsed.scheme, host=parsed.hostname,
                         port=parsed.port, user=unquote(parsed.username) if parsed.username else None,
                         password=unquote(parsed.password) if parsed.password else None,
                         dbname=parsed.path.lstrip('/'))
        if attrs.pop('implementation', 'sqlite') not in ('postgres', 'postgres3', 'postgresql'):
            raise GenropyConnectionError('The Genropy instance must use PostgreSQL')
        return operations.connection_params({key: value for key, value in attrs.items()
                                            if value is not None and value != ''})
    except GenropyConnectionError:
        raise
    except Exception:
        raise GenropyConnectionError(
            'Invalid Genropy database configuration; check connection fields and environment variables'
        ) from None


def introspect_instance(instance, schemas=None):
    """Read the actual database through Migration; retain no connection settings."""
    connection = connection_from_instance(instance)
    try:
        if schemas is None:
            return operations.introspect(connection)
        return operations.introspect(connection, schemas=schemas)
    except Exception:
        raise GenropyConnectionError(
            'Cannot read the instance database; check PostgreSQL access and install asqueel-dbmanager[postgresql]'
        ) from None
