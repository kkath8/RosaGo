"""Local candidate: deny app authority and journal before one provider logout.

Receipts are encrypted by the shared store and independently revision-fenced.
A claimed call is never repeated, including after a crash or unknown result.
Reconciliation uses read-only provider checks; None never means confirmed.
"""
from session_authority import RevisionConflict
from session_realms import SessionStorageUnavailable


class DurableLogout:
    def __init__(self, realms, *, issuer, sign_out, session_check, revocation_check=None):
        if (set(realms)!={'user','admin'} or not callable(sign_out) or not callable(session_check)
                or (revocation_check is not None and not callable(revocation_check))):
            raise ValueError('Invalid logout dependencies.')
        self.realms, self.issuer, self.sign_out, self.session_check=realms,issuer,sign_out,session_check
        self.revocation_check=revocation_check

    def __call__(self, realm, web_handle):
        backend=self.realms[realm]
        if not web_handle: return False
        receipt=backend.snapshot('logout',web_handle)
        if receipt.data is None:
            parent=backend.snapshot('web',web_handle)
            reads={parent.key:parent,receipt.key:receipt}
            updates={parent.key:(None,parent.now,{})}
            record=None
            if parent.data and parent.data['values'].get('auth_session_id'):
                auth=backend.snapshot('auth',parent.data['values']['auth_session_id'])
                reads[auth.key]=auth; updates[auth.key]=(None,parent.now,{})
                record=auth.data['record'] if auth.data else None
            # Missing credentials cannot establish provider signout. Deny the
            # app anyway; never infer a successful provider operation.
            state={'state':'prepared','record':record,'web_handle':web_handle} if record else {'state':'unconfirmed'}
            updates[receipt.key]=(state,receipt.now+28800,{})
            backend.atomic(reads,updates)
        return self.reconcile(realm,web_handle)

    def reconcile(self,realm,web_handle):
        backend=self.realms[realm]; snap=backend.snapshot('logout',web_handle)
        if not snap.data: return False
        state=snap.data['state']
        if state=='confirmed': return True
        record=snap.data.get('record')
        if record is None: return False
        if state=='prepared':
            # Persist ownership of the one permitted provider call first. A CAS
            # conflict/unknown commit never authorizes the external mutation.
            try:
                backend.write(snap,{**snap.data,'state':'attempted'},snap.meta['expires'])
            except RevisionConflict:
                return False
            try:
                acknowledged=(self.sign_out(record,self.issuer,realm) is True
                              and self.session_check(record,self.issuer,realm) is False)
            except Exception: acknowledged=False
        else:
            try: acknowledged=self.session_check(record,self.issuer,realm) is False
            except Exception: acknowledged=False
        # Provider-row absence is not independent revocation proof: an Auth
        # restore can recreate that row. Unknown/expired/unenrolled authority
        # state cannot stand in for the permanent tombstone either. This check
        # is read-only and never retries the claimed provider logout operation.
        if acknowledged and self.revocation_check is not None:
            try: acknowledged=self.revocation_check(record,self.issuer,realm) is True
            except Exception: acknowledged=False
        if not acknowledged: return False
        snap=backend.snapshot('logout',web_handle)
        if not snap.data: raise SessionStorageUnavailable('Logout receipt is unavailable.')
        backend.write(snap,{'state':'confirmed'},snap.meta['expires'])
        return True

    def reconcile_pending(self,realm,*,cursor='',limit=8):
        """Internal bounded read-only provider reconciliation after worker death.

        Cache enumeration supplies candidates only. Backend validates each
        against the independent ledger before returning an encrypted receipt.
        No provider mutation is initiated here, even for prepared receipts.
        No HTTP endpoint or background job is installed by this method.
        """
        snapshots,next_cursor=self.realms[realm].logout_receipts(cursor=cursor,limit=limit)
        confirmed=0
        for snap in snapshots:
            if snap.data and snap.data.get('state')=='attempted':
                confirmed+=self.reconcile(realm,snap.data['web_handle']) is True
        return {'confirmed':confirmed,'next_cursor':next_cursor}
