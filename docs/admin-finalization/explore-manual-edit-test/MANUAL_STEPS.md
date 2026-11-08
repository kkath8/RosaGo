# Isolated manual edit walkthrough

Use only the current fixture URL in REPORT.md, in a fresh Incognito/InPrivate window. This server has two in-memory test destinations and mocked Storage. Never use a real account or a normal RosaGo server for this checklist.

## 1. Open the fixture Admin interface

At the isolated `/admin/login` page, use the existing demo's **synthetic-only** login:

- Email: `admin-b@example.invalid`
- Dummy fixture password: `Local-test-password-1!`

These public fixture constants are not a real account or password. They are accepted only by the test adapter; no Supabase Auth sign-in is sent. Then open **Destinations** and choose **Edit Destination** for **Manual Test Garden**. Keep **Unrelated Test Museum** unchanged.

Confirm the Garden starts with name Manual Test Garden, description Isolated saved description., category Nature, address Isolated Santa Rosa test address, latitude 14.3, longitude 121.1, Environment Indoor, and a blue saved photo.

## 2. Save ordinary changes

Set these values and click Save Changes once:

| Control | Test value |
| --- | --- |
| Destination name | Controlled Garden Edit |
| Description | Controlled manual edit only. |
| Category | Attraction |
| Address | Isolated updated test address |
| Latitude | 14.31 |
| Longitude | 121.12 |
| Environment | Outdoor |

Expected: details show the new information and Published status. Reopen Edit and confirm the values persisted. The other destination must not change.

## 3. Replace the photo

Use the edit form's file picker to choose the red **replacement-test.png** fixture from this report directory, then save once. Its full local path is:

```text
C:\Users\USER\OneDrive - Polytechnic University of the Philippines\Documents\Kath\Capstone\Capstone 2\RosaGo(User)\docs\admin-finalization\explore-manual-edit-test\replacement-test.png
```

Expected: the saved blue cover becomes red. This uses a mocked Storage request and serves image bytes from localhost; no local application image file or real Storage object changes.

## 4. Trigger server validation while removing the photo

Reopen Edit. Select **Remove the saved photo when saving**, change Description to **Validation correction retained.**, and clear **Longitude only**, leaving Latitude 14.31. Submit once. The coordinate controls are optional individually, so this reaches the server's pair-validation rule without bypassing browser validation.

Expected: a coordinate-pair validation error; all entered text, category, latitude and environment remain; Longitude remains blank; removal stays checked. Nothing is saved on this failed submission.

Correct Longitude to **121.12**, leave removal checked, and save once. Expected: successful details page with the corrected description and no cover photo.

## 5. Check User Explore

Open the same isolated origin's `/places` in another tab. Refresh as needed. Confirm **Controlled Garden Edit**, its current category/address, and the unchanged Museum. Open the Garden details and confirm its description/environment/location and removed photo. No second Garden should exist.

Report only the visible pass/fail outcomes or the first unexpected error. Do not share credentials, cookies, tokens, browser exports or screenshots containing account information. Stop on wrong identity, duplicate rows, unrelated changes, unexpected permissions, provider errors or uncertain saves. Do not retry automatically.
