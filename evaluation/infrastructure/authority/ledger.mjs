// Portable SQLite authority core. No credentials or session payloads belong here.
// storage: Cloudflare DurableObjectStorage (sql.exec + transactionSync).
const scalar = v => typeof v === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(v);
const identity = v => typeof v === 'string' && /^[A-Za-z0-9_-]{16,128}$/.test(v);
const normalize = v => Array.isArray(v) ? v.map(normalize)
  : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k=>[k,normalize(v[k])])) : v;
const canonical = v => JSON.stringify(normalize(v));
class Closed extends Error {}
class Conflict extends Error {}
export class Ledger {
  constructor(storage, binding, clock = () => Date.now() / 1000) {
    this.storage = storage; this.binding = binding; this.clock = clock;
    this.sql = storage.sql;
    this.sql.exec('CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL NOT NULL, size INTEGER NOT NULL)');
    this.sql.exec('CREATE INDEX IF NOT EXISTS records_expiry ON records(expires)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS receipts (nonce TEXT PRIMARY KEY, request TEXT NOT NULL, response TEXT NOT NULL, expires REAL NOT NULL)');
    this.sql.exec('CREATE TABLE IF NOT EXISTS tombstones (key TEXT PRIMARY KEY, expires REAL NOT NULL)');
  }
  rows(sql, ...args) { return [...this.sql.exec(sql, ...args)]; }
  control() { const row = this.rows('SELECT value FROM control WHERE id=1')[0]; return row ? JSON.parse(row.value) : null; }
  // Separate operator path; an application request can never call this method.
  initialize(config) {
    return this.storage.transactionSync(() => {
      if (this.control() || !identity(config.authority_id) || !identity(config.incarnation)
          || !scalar(config.namespace) || !scalar(config.epochs?.user) || !scalar(config.epochs?.admin)
          || config.epochs.user === config.epochs.admin
          || config.authority_id !== this.binding.authority_id || config.incarnation !== this.binding.incarnation)
        throw new Closed();
      const value = { ...config, state: 'OPEN', generation: 1, sequence: 0,
        limits: {records: 4096, bytes: 33554432} };
      this.sql.exec('INSERT INTO control VALUES(1,?)', JSON.stringify(value));
      return true;
    });
  }
  block() {
    return this.storage.transactionSync(() => {
      const c = this.control(); if (!c) throw new Closed();
      c.state = 'BLOCKED'; c.generation++; c.sequence++;
      this.sql.exec('UPDATE control SET value=? WHERE id=1', JSON.stringify(c));
      return true;
    });
  }
  descriptor(c) { return {state:c.state, generation:c.generation, epochs:c.epochs, limits:c.limits}; }
  scope(c, a) {
    if (a.namespace !== c.namespace || !['user','admin'].includes(a.realm) || a.epoch !== c.epochs[a.realm]) throw new Closed();
    return `${c.namespace}:sessions:v3:${a.realm}:${a.epoch}`;
  }
  key(prefix, key) {
    if (typeof key !== 'string' || !key.startsWith(prefix + ':')
        || !/^[a-z_]{1,20}:[a-f0-9]{64}$/.test(key.slice(prefix.length + 1))) throw new Closed();
  }
  current(key, now) {
    const row = this.rows('SELECT value FROM records WHERE key=? AND expires>?', key, now)[0];
    return row ? JSON.parse(row.value) : null;
  }
  exchange(request) {
    let control = this.control();
    const reply = (status, payload=null) => ({version:1, request_id:request?.request_id,
      authority_id:this.binding.authority_id, incarnation:this.binding.incarnation,
      sequence:control?.sequence ?? 0, status, payload});
    try {
      return this.storage.transactionSync(() => {
        control = this.control(); const c = control; const now = this.clock();
        if (!c || c.state !== 'OPEN' || c.authority_id !== this.binding.authority_id
            || c.incarnation !== this.binding.incarnation || request?.version !== 1
            || request.authority_id !== c.authority_id || request.incarnation !== c.incarnation
            || !identity(request.request_id) || JSON.stringify(request).length > 65536) throw new Closed();
        const a = request.arguments; if (!a || typeof a !== 'object' || Array.isArray(a)) throw new Closed();
        if (request.operation === 'health') return reply('ok', true);
        if (a.namespace !== c.namespace) throw new Closed();
        if (request.operation === 'descriptor') return reply('ok', this.descriptor(c));
        const prefix = this.scope(c, a);
        if (!Number.isFinite(a.now) || Math.abs(now-a.now) > 2) throw new Closed();
        if (request.operation === 'read') {
          this.key(prefix,a.key); return reply('ok',this.current(a.key,now));
        }
        if (request.operation !== 'commit' || a.generation !== c.generation) throw new Closed();
        const previous = this.rows('SELECT request,response FROM receipts WHERE nonce=?',request.request_id)[0];
        if (previous) {
          if (previous.request !== JSON.stringify(request)) throw new Closed();
          return JSON.parse(previous.response);
        }
        const expected = a.expected, changes = a.changes;
        if (!expected || !changes || Array.isArray(expected) || Array.isArray(changes)
            || !Object.keys(expected).length || Object.keys(expected).length > 8
            || !Object.keys(changes).length) throw new Closed();
        for (const [key,value] of Object.entries(expected)) {
          this.key(prefix,key);
          if (canonical(this.current(key,now)) !== canonical(value)) throw new Conflict();
          if (value===null && this.rows('SELECT key FROM tombstones WHERE key=? AND expires>?',key,now).length) throw new Conflict();
        }
        this.sql.exec('DELETE FROM records WHERE expires<=?',now);
        this.sql.exec('DELETE FROM receipts WHERE expires<=?',now);
        this.sql.exec('DELETE FROM tombstones WHERE expires<=?',now);
        if (this.rows('SELECT count(*) n FROM receipts')[0].n >= 8192) throw new Closed();
        for (const [key,value] of Object.entries(changes)) {
          if (!Object.hasOwn(expected,key)) throw new Closed();
          this.key(prefix,key);
          if (value !== null && (typeof value !== 'object' || Array.isArray(value)
              || !/^[a-f0-9]{64}$/.test(value.digest) || !Number.isInteger(value.size)
              || value.size < 1 || value.size > 45000 || !Number.isFinite(value.expires)
              || value.expires <= now || value.expires > now+28801
              || value.realm_scope !== prefix || value.scope !== key.slice(0,key.lastIndexOf(':'))
              || JSON.stringify(value).length > 2048)) throw new Closed();
          this.sql.exec('DELETE FROM records WHERE key=?',key);
          if (value !== null) this.sql.exec('INSERT INTO records VALUES(?,?,?,?)',key,JSON.stringify(value),value.expires,value.size);
          else this.sql.exec('INSERT INTO tombstones VALUES(?,?) ON CONFLICT(key) DO UPDATE SET expires=excluded.expires',key,now+28802);
        }
        const total=this.rows('SELECT count(*) n, coalesce(sum(size),0) bytes FROM records')[0];
        if (total.n > c.limits.records || total.bytes > c.limits.bytes
            || this.rows('SELECT count(*) n FROM tombstones')[0].n > 8192) throw new Closed();
        c.sequence++;
        this.sql.exec('UPDATE control SET value=? WHERE id=1',JSON.stringify(c));
        const response=reply('ok',true);
        // Commits carry a server-checked +/-2s timestamp. Five seconds covers
        // the entire accepted replay window, including a future-skewed request.
        this.sql.exec('INSERT INTO receipts VALUES(?,?,?,?)',request.request_id,JSON.stringify(request),JSON.stringify(response),now+5);
        return response;
      });
    } catch (error) {
      // Re-read after rollback. Never disclose data, exceptions or SQL.
      control=this.control(); return reply(error instanceof Conflict ? 'conflict' : 'closed');
    }
  }
}
