"""Interactive disposable-profile tests. Never run automatically or from Flask.

Only names on the two authenticated, prevalidated test profiles are restored.
An unexpected missing profile or changed protected column stops all writes.
Original values and credentials exist only in memory. Process termination or
loss of connectivity can prevent restoration; that is reported, never a PASS.
"""
import logging
import sys
from uuid import uuid4

import httpx
import verify_profile_reads as reads


class TestFailure(Exception):
    pass


class CriticalFailure(Exception):
    pass


class WriteVerifier:
    def __init__(self, a, b, anonymous, a_id, b_id):
        self.clients = {'A': a, 'B': b, 'anon': anonymous}
        self.ids = {'A': a_id, 'B': b_id}
        self.original = {}
        self.candidate = str(uuid4())
        self.marker = 'RosaGO security test ' + uuid4().hex

    def validate(self, label):
        if label == 'anon':
            if ('Authorization' in self.clients[label].headers
                    or self.clients[label].cookies):
                raise TestFailure()
        elif reads.identity(self.clients[label], label)[0] != self.ids[label]:
            raise TestFailure()

    def fetch(self, label, target=None):
        params = {'select': 'id,first_name,last_name,created_at'}
        if target is not None:
            params['id'] = 'eq.' + target
        response = reads.request(self.clients[label], 'GET', '/rest/v1/profiles', params=params)
        if response.status_code != 200:
            raise TestFailure()
        data = response.json()
        if not isinstance(data, list):
            raise TestFailure()
        return data

    def snapshot(self, label):
        data = self.fetch(label, self.ids[label])
        if (len(data) != 1 or not isinstance(data[0], dict)
                or set(data[0]) != {'id', 'first_name', 'last_name', 'created_at'}
                or data[0]['id'] != self.ids[label] or not data[0]['created_at']):
            if self.original:
                raise CriticalFailure()
            raise TestFailure()
        return data[0]

    def setup(self):
        if self.ids['A'] == self.ids['B'] or self.candidate in self.ids.values():
            raise TestFailure()
        expected = {'A': ('Test', 'User'), 'B': ('Profile', 'Test')}
        originals = {}
        for label in ('A', 'B'):
            self.validate(label)
            row = self.snapshot(label)
            if (row['first_name'], row['last_name']) != expected[label]:
                raise TestFailure()
            if self.fetch(label) != [row]:
                raise TestFailure()
            originals[label] = row
        self.validate('anon')
        self.original = originals

    def send(self, actor, target, method, payload=None):
        # Narrow write gateway: no caller-supplied paths, filters, or headers.
        if actor not in self.clients or target not in self.ids.values():
            raise TestFailure()
        if method == 'PATCH':
            if (not isinstance(payload, dict) or not payload
                    or not set(payload) <= {'first_name', 'last_name', 'id', 'created_at'}):
                raise TestFailure()
            if 'id' in payload and payload['id'] != self.candidate:
                raise TestFailure()
        elif method == 'DELETE':
            if actor != 'A' or target != self.ids['A'] or payload is not None:
                raise TestFailure()
        elif method == 'POST':
            if actor != 'A' or payload != {'id': self.candidate}:
                raise TestFailure()
        else:
            raise TestFailure()
        self.validate(actor)
        params = {} if method == 'POST' else {'id': 'eq.' + target}
        kwargs = {'json': payload} if payload is not None else {}
        return self.clients[actor].request(method, '/rest/v1/profiles',
            params=params, headers={'Prefer': 'return=representation',
                                    'Content-Profile': 'public'}, **kwargs)

    def state(self):
        current = {label: self.snapshot(label) for label in ('A', 'B')}
        for label, row in current.items():
            for field in ('id', 'created_at'):
                if row[field] != self.original[label][field]:
                    raise CriticalFailure()
        return current

    def restore(self, current):
        # Restore only name changes on known existing rows with unchanged IDs
        # and timestamps. Never insert/reconstruct a missing profile.
        for label in ('A', 'B'):
            changed = {field: self.original[label][field]
                       for field in ('first_name', 'last_name')
                       if current[label][field] != self.original[label][field]}
            if changed:
                # Do not overwrite unrelated concurrent edits.
                if any(current[label][field] != self.marker for field in changed):
                    raise TestFailure()
                response = self.send(label, self.ids[label], 'PATCH', changed)
                if response.status_code != 200:
                    raise TestFailure()
        if self.state() != self.original:
            raise TestFailure()

    @staticmethod
    def denied(response):
        if response is None:
            return False
        try:
            error = response.json()
        except ValueError:
            return False
        if not isinstance(error, dict):
            return False
        code = error.get('code')
        if code == '23503':
            print('FAIL: FOREIGN_KEY_ERROR_IS_NOT_PERMISSION_DENIAL')
        elif code == '23505':
            print('FAIL: DUPLICATE_KEY_ERROR_IS_NOT_PERMISSION_DENIAL')
        messages = {
            'permission denied for table profiles',
            'permission denied for column id of relation profiles',
            'permission denied for column created_at of relation profiles',
            'new row violates row-level security policy for table "profiles"',
        }
        return (response.status_code in (401, 403) and code == '42501'
                and error.get('message') in messages)

    def test(self, label, actor, target, method, payload, expected, success):
        print('CHECK: ' + label)  # Labels are fixed by run(), never provider data.
        response = None
        interrupted = False
        try:
            response = self.send(actor, self.ids[target], method, payload)
        except KeyboardInterrupt:
            interrupted = True
        except Exception:
            # A timeout can follow a committed update. Read back and attempt
            # only safe name restoration before stopping; never retry the test.
            pass
        try:
            current = self.state()
            altered = current != self.original
            critical = expected != 'allow' and altered
            if critical:
                # Restore name-only damage through its owner, then stop even
                # if the response body is malformed or claims an error.
                self.restore(current)
                raise CriticalFailure()
            if expected == 'allow':
                wanted = {owner: dict(row) for owner, row in self.original.items()}
                wanted[target].update(payload)
                ok = response is not None and response.status_code == 200 and current == wanted
                if ok:
                    ok = response.json() == [wanted[target]]
            elif expected == 'cross':
                ok = self.denied(response)
                if response is not None and response.status_code == 200:
                    ok = response.json() == []
                ok = ok and not altered
            else:
                ok = self.denied(response) and not altered
                if response is not None and 200 <= response.status_code < 300:
                    critical = True
            # For the random INSERT candidate, RLS can hide a row from both
            # callers. These checks detect visibility, not privileged absence.
            if method == 'POST':
                visible = self.fetch('A', self.candidate) or self.fetch('B', self.candidate)
                if visible:
                    critical = True
                    print('CRITICAL SECURITY FAILURE: Unexpected INSERT row visible')
            self.restore(current)
            for owner in ('A', 'B'):
                self.validate(owner)
            if critical:
                raise CriticalFailure()
            if not ok or interrupted:
                raise TestFailure()
        except CriticalFailure:
            raise
        except Exception:
            # A malformed response must not prevent safe restoration.
            try:
                self.restore(self.state())
            except CriticalFailure:
                raise
            except Exception:
                print('FAIL: Original profile restoration not confirmed; manual review required')
            raise TestFailure() from None
        print('PASS: ' + success)
        if expected == 'allow':
            print('PASS: User ' + target + ' original names restored')

    def run(self):
        self.setup()
        print('PASS: Both disposable identities and initial isolation validated')
        for label, actor, target, method, payload, expected, success in (
            ('D1', 'A', 'A', 'PATCH', {'first_name': self.marker}, 'allow', 'User A can update own first_name'),
            ('D2', 'A', 'A', 'PATCH', {'last_name': self.marker}, 'allow', 'User A can update own last_name'),
            ('D3', 'B', 'B', 'PATCH', {'first_name': self.marker, 'last_name': self.marker}, 'allow', 'User B can update own names'),
            ('E', 'A', 'B', 'PATCH', {'first_name': self.marker}, 'cross', 'User A cannot update User B profile'),
            ('F1', 'A', 'A', 'PATCH', {'id': self.candidate}, 'deny', 'User A cannot update id'),
            ('F2', 'A', 'A', 'PATCH', {'created_at': '2000-01-01T00:00:00+00:00'}, 'deny', 'User A cannot update created_at'),
            ('F3', 'A', 'A', 'PATCH', {'first_name': self.marker, 'created_at': '2000-01-01T00:00:00+00:00'}, 'deny', 'Combined protected-column update denied'),
            ('G', 'A', 'A', 'POST', {'id': self.candidate}, 'deny', 'Arbitrary profile INSERT denied'),
            ('H', 'A', 'A', 'DELETE', None, 'deny', 'Profile DELETE denied'),
            ('J', 'anon', 'A', 'PATCH', {'first_name': self.marker}, 'deny', 'Anonymous UPDATE denied'),
        ):
            self.test(label, actor, target, method, payload, expected, success)
        if self.state() != self.original:
            raise TestFailure()
        print('PASS: Original profile data restored')
        print('PASS: WRITE RLS verified')


def main():
    logging.disable(logging.CRITICAL)
    try:
        url, key = reads.configuration()
        options = dict(base_url=url, headers={'apikey': key, 'Accept-Profile': 'public'},
                       timeout=20, follow_redirects=False, trust_env=False)
        with httpx.Client(**options) as a, httpx.Client(**options) as b, httpx.Client(**options) as anonymous:
            a_id = reads.sign_in(a, 'A')
            b_id = reads.sign_in(b, 'B')
            WriteVerifier(a, b, anonymous, a_id, b_id).run()
        return 0
    except CriticalFailure:
        print('CRITICAL SECURITY FAILURE: Forbidden operation succeeded or protected profile state changed; stopped')
    except reads.VerificationError as error:
        category = error.args[0] if error.args else None
        print(category if category in reads.CATEGORIES else 'FAIL: Identity or configuration invalid')
    except (Exception, KeyboardInterrupt):
        print('FAIL: Verification incomplete; last CHECK identifies the failed test')
    print('FAIL: WRITE RLS not verified')
    return 1


if __name__ == '__main__':
    sys.exit(main())
