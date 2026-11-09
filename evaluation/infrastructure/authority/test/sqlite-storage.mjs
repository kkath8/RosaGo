// Test shim only. Actual workerd behavior is exercised separately.
import { DatabaseSync } from 'node:sqlite';
export function sqliteStorage(path) {
  const db=new DatabaseSync(path);
  db.exec('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=500');
  return {db,sql:{exec(sql,...args){
    const statement=db.prepare(sql);
    return statement.columns().length ? statement.all(...args) : (statement.run(...args),[]);
  }},transactionSync(callback){
    db.exec('BEGIN IMMEDIATE');
    try {const value=callback();db.exec('COMMIT');return value;}
    catch(e){db.exec('ROLLBACK');throw e;}
  }};
}
