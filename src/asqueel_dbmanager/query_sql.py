"""PostgreSQL is the SQL validator; execute bounded reads with safe diagnostics."""

import json
import re

from . import operations
from .query_profiles import QueryError

# Provider feedback is intentionally made from SQLSTATE, not raw server text:
# PostgreSQL diagnostics can include database values, connection details or UDF output.
REPAIRABLE_ERRORS = {
    '42601': 'SQL syntax error',
    '42703': 'Undefined column',
    '42P01': 'Undefined table or missing FROM-clause entry',
    '42702': 'Ambiguous column reference',
    '42883': 'Undefined function or operator for the argument types',
    '42804': 'Datatype mismatch',
    '42803': 'Invalid grouping or aggregate expression',
    '42P10': 'Invalid column reference',
    '42846': 'Cannot convert between the specified types',
    '42712': 'Duplicate table alias',
    '42P09': 'Ambiguous alias',
    '42P18': 'Indeterminate parameter datatype',
    '22P02': 'Invalid text representation for the required datatype',
    '22007': 'Invalid date or time format',
    '22008': 'Date or time value out of range',
    '22003': 'Numeric value out of range',
    '22012': 'Division by zero',
}


class ReadQueryError(QueryError):
    """A sanitized execution failure which may allow an LLM correction."""

    def __init__(self, code, *, position=None):
        self.retryable = code in REPAIRABLE_ERRORS or code == 'PARAMETERS'
        message = REPAIRABLE_ERRORS.get(code, {
            'PARAMETERS': 'SQL parameters do not match named psycopg placeholders',
            '42501': 'Insufficient database privileges',
            '25006': 'Operation is not allowed in a read-only transaction',
            '57014': 'Query canceled or statement timeout exceeded',
            '55P03': 'Database lock is unavailable',
        }.get(code, 'Database execution failed'))
        self.diagnostic = {'code': code, 'message': message}
        if position and str(position).isdigit():
            self.diagnostic['statement_position'] = int(position)
        super().__init__(message)


def prepare_sql(sql, params):
    """Check the response shape only; no parsing, name resolution or rewriting."""
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 40000:
        raise QueryError('Invalid SQL proposal')
    if (not isinstance(params, dict)
            or any(not isinstance(k, str) or not re.fullmatch(r'[A-Za-z_]\w*', k) for k in params)):
        raise QueryError('Invalid SQL parameters')
    try:
        json.dumps(params, allow_nan=False)
    except (TypeError, ValueError):
        raise QueryError('Invalid SQL parameters') from None
    return sql.strip().removesuffix(';').rstrip()


def execute_read(connection, sql, params, max_rows=200):
    """Fresh read-only transaction and a single prepared statement, never a script.

    Read-only mode is not a function sandbox. Use a least-privilege PostgreSQL
    role: its grants, including EXECUTE grants, are the authorization boundary.
    """
    import psycopg

    sql = prepare_sql(sql, params)
    if not isinstance(max_rows, int) or isinstance(max_rows, bool) or not 1 <= max_rows <= 500:
        raise QueryError('max_rows must be between 1 and 500')
    try:
        bound_sql = re.sub(r'%(?!\([A-Za-z_]\w*\)s)', '%%', sql)
        with operations.database(connection) as db, db.adapter.connect() as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            conn.execute("SET LOCAL statement_timeout = '15s'")
            conn.execute("SET LOCAL lock_timeout = '2s'")
            conn.execute('SET LOCAL search_path = pg_catalog')
            with conn.cursor() as cursor:
                # PostgreSQL's extended protocol rejects multiple commands, even
                # if SQL tries to break out of the subquery wrapper.
                cursor.execute(
                    f'SELECT * FROM (\n{bound_sql}\n) AS dbmanager_result LIMIT {max_rows + 1}',
                    params, prepare=True)
                columns = [c.name for c in cursor.description]
                rows = cursor.fetchmany(max_rows + 1)
            conn.rollback()
        result = json.loads(json.dumps({'columns': columns, 'rows': rows[:max_rows],
                                       'truncated': len(rows) > max_rows}, default=str))
        if len(json.dumps(result).encode()) > 2_000_000:
            raise QueryError('Query result exceeds the response size limit; select fewer columns')
        return result
    except QueryError:
        raise
    except psycopg.Error as error:
        code = error.sqlstate
        if code is None and isinstance(error, psycopg.ProgrammingError):
            code = 'PARAMETERS'
        raise ReadQueryError(code or 'DATABASE',
                             position=error.diag.statement_position) from None
    except Exception:
        raise QueryError('Read query failed; check permissions, structure or query limits') from None
