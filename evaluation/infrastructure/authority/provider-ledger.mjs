// Independent provider admission and permanent revocation, separate from Auth DB.
// No JWTs, passwords, refresh tokens or application payloads are stored here.
const uuid = v => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v);
const id = v => typeof v === 'string' && /^[A-Za-z0-9_-]{16,128}$/.test(v);
export class ProviderLedger {
  constructor(storage, ledger, issuer, clock = () => Date.now()/1000) {
    this.storage=storage; this.ledger=ledger; this.issuer=issuer; this.clock=clock;
    storage.sql.exec(`CREATE TABLE IF NOT EXISTS provider_sessions (
      sid TEXT PRIMARY KEY, uid TEXT NOT NULL, deadline REAL NOT NULL, revoked INTEGER NOT NULL)`);
    storage.sql.exec(`CREATE TABLE IF NOT EXISTS provider_limits (
      sid TEXT PRIMARY KEY, uid TEXT NOT NULL, deadline REAL NOT NULL)`);
  }
  exchange(operation, request) {
    return this.storage.transactionSync(() => {
      const c=this.ledger.control(), now=this.clock(), r=request;
      if (!c || c.state!=='OPEN' || c.authority_id!==this.ledger.binding.authority_id
          || c.incarnation!==this.ledger.binding.incarnation
          || !['enroll','check','revoke','inspect','constrain'].includes(operation)
          || r?.version!==1 || !id(r.nonce) || r.authority_id!==c.authority_id
          || r.incarnation!==c.incarnation || r.namespace!==c.namespace
          || typeof this.issuer!=='string' || !this.issuer.startsWith('https://')
          || r.issuer!==this.issuer || !uuid(r.uid) || !uuid(r.sid)
          || !Number.isFinite(r.now) || Math.abs(now-r.now)>5) throw new Error('Closed');
      const rows=(sql,...args)=>[...this.storage.sql.exec(sql,...args)];
      let row=rows('SELECT * FROM provider_sessions WHERE sid=?',r.sid)[0];
      let limit=rows('SELECT * FROM provider_limits WHERE sid=?',r.sid)[0];
      if ((row && row.uid!==r.uid) || (limit && limit.uid!==r.uid)) throw new Error('Closed');
      // Never garbage collect tombstones or re-admit an expired/revoked SID.
      // Capacity exhaustion requires a reviewed incarnation cutover, not reset.
      if (operation==='enroll') {
        if (!Number.isFinite(r.deadline) || r.deadline<=now || r.deadline>now+28800
            || (limit && limit.deadline<=now)
            || (row && (row.revoked || row.deadline<=now))) throw new Error('Closed');
        if (!row) {
          if (rows('SELECT count(*) n FROM provider_sessions')[0].n>=100000) throw new Error('Closed');
          this.storage.sql.exec('INSERT INTO provider_sessions VALUES(?,?,?,0)',r.sid,r.uid,r.deadline);
        }
      } else if (operation==='constrain') {
        if (!Number.isFinite(r.deadline) || r.deadline<=0) throw new Error('Closed');
        if (!limit && rows('SELECT count(*) n FROM provider_limits')[0].n>=100000) throw new Error('Closed');
        this.storage.sql.exec(`INSERT INTO provider_limits VALUES(?,?,?) ON CONFLICT(sid)
          DO UPDATE SET deadline=min(deadline,excluded.deadline)`,r.sid,r.uid,r.deadline);
      } else if (operation==='revoke') {
        if (row && row.uid!==r.uid) throw new Error('Closed');
        if (!row && rows('SELECT count(*) n FROM provider_sessions')[0].n>=100000) throw new Error('Closed');
        this.storage.sql.exec(`INSERT INTO provider_sessions VALUES(?,?,0,1)
          ON CONFLICT(sid) DO UPDATE SET revoked=1`,r.sid,r.uid);
      }
      row=rows('SELECT * FROM provider_sessions WHERE sid=?',r.sid)[0];
      limit=rows('SELECT * FROM provider_limits WHERE sid=?',r.sid)[0];
      const expired=(!!row && row.deadline<=now) || (!!limit && limit.deadline<=now);
      const active=!!row && !row.revoked && !expired;
      return {version:1,nonce:r.nonce,authority_id:c.authority_id,incarnation:c.incarnation,
        namespace:c.namespace,issuer:this.issuer,uid:r.uid,sid:r.sid,now,
        active, revoked:!!row?.revoked, known:!!row, expired};
    });
  }
}
