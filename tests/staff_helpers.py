import re


def staff_login(
    client,
    staff_id=1,
    pin="1234",
    *,
    headers=None,
    base_url=None,
    environ_overrides=None,
    follow_redirects=False,
):
    request_options = {}
    if headers is not None:
        request_options["headers"] = headers
    if base_url is not None:
        request_options["base_url"] = base_url
    if environ_overrides is not None:
        request_options["environ_overrides"] = environ_overrides
    page = client.get("/login", **request_options)
    match = re.search(
        r'name="login_csrf_token" value="([^"]+)"',
        page.get_data(as_text=True),
    )
    if not match:
        raise AssertionError("missing pre-session CSRF token on /login")
    return client.post(
        "/login",
        data={
            "staff_id": str(staff_id),
            "pin": str(pin),
            "login_csrf_token": match.group(1),
        },
        follow_redirects=follow_redirects,
        **request_options,
    )
