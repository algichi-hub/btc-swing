"""F3 migration executed by privileged migration user, never web/worker."""
from __future__ import annotations
import hashlib
from pathlib import Path
from app.storage.postgres import connect_pg
VERSION='0002_worker'

def apply_worker_migration():
    p=Path(__file__).resolve().parents[2]/'migrations'/'0002_worker.sql'
    sql=p.read_text(encoding='utf-8')
    checksum=hashlib.sha256(sql.encode('utf-8')).hexdigest()
    statements=[x.strip() for x in '\n'.join(line for line in sql.splitlines() if not line.lstrip().startswith('--')).split(';') if x.strip()]
    with connect_pg() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)',(5022026,))
        rec=conn.execute('SELECT checksum FROM schema_migrations WHERE version=%s',(VERSION,)).fetchone()
        if rec is not None:
            if rec['checksum'] != checksum: raise RuntimeError('F3 schema checksum mismatch')
            return False
        for item in statements:conn.execute(item)
        conn.execute('INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)',(VERSION,checksum))
    return True
if __name__=='__main__':apply_worker_migration()