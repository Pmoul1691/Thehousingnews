# Auth Testing Playbook - The Ultradian Network

Emergent-managed Google Auth. No app-managed passwords. To test without doing a
real Google sign-in, inject a user + session directly into MongoDB, then send the
session_token as a Bearer header or as a cookie.

## 1. Create test user + session

```bash
mongosh --eval "
use('test_database');
var userId = 'user_test' + Date.now();
var token = 'tok_test_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.member.' + Date.now() + '@example.com',
  name: 'Test Member',
  picture: '',
  is_admin: false,
  status: 'approved',
  source: 'manual_test',
  created_at: new Date().toISOString(),
  last_login_at: new Date().toISOString()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: token,
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString()
});
print('TOKEN: ' + token);
print('USER:  ' + userId);
"
```

For admin (needed to test /api/applications approve/decline):

```bash
mongosh --eval "
use('test_database');
var userId = 'user_admin' + Date.now();
var token = 'tok_admin_' + Date.now();
db.users.insertOne({
  user_id: userId, email: 'peter@1691inc.com', name: 'Peter Moulton',
  picture: '', is_admin: true, status: 'approved', source: 'manual_test',
  created_at: new Date().toISOString(), last_login_at: new Date().toISOString()
});
db.user_sessions.insertOne({
  user_id: userId, session_token: token,
  created_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 7*24*60*60*1000).toISOString()
});
print('ADMIN TOKEN: ' + token);
"
```

## 2. Backend API tests

```bash
BASE=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
TOKEN=<paste from step 1>

# Auth verification
curl -s -X GET "$BASE/api/auth/me" -H "Authorization: Bearer $TOKEN"

# Profile create
curl -s -X PUT "$BASE/api/profile" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Test Member","market":"Chicago, IL","bio":"Selling homes in Lincoln Park.","objectives":["List 12 homes by June","Build a 3-person team","Write daily"]}'

# Create a post
curl -s -X POST "$BASE/api/posts" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"Saw a vacant 4-flat on Wabansia. Three offers in 48 hours."}'

# Public feed
curl -s "$BASE/api/posts/public"

# Release window
curl -s "$BASE/api/release-window"
```

## 3. Browser testing (Playwright)

```python
await page.context.add_cookies([{
    "name": "session_token",
    "value": "<TOKEN>",
    "domain": "<host of REACT_APP_BACKEND_URL without scheme>",
    "path": "/",
    "httpOnly": True,
    "secure": True,
    "sameSite": "None"
}])
await page.goto(f"{frontend_url}/feed")
```

## Checklist
- [ ] `GET /api/auth/me` returns 200 with `user_id` (custom UUID) when valid token sent.
- [ ] `_id` field never appears in any response.
- [ ] `POST /api/posts` rejects unapproved users with 403.
- [ ] `POST /api/applications/{id}/approve` requires admin (403 otherwise).
- [ ] Logout deletes the session row and clears the cookie.
