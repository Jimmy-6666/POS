import re


def form_csrf(client, path):
    html = client.get(path).get_data(as_text=True)
    matches = re.findall(r'name="csrf_token" value="([^"]+)"', html)
    if not matches:
        raise AssertionError(f"missing csrf token on {path}")
    return matches[-1]


def register_customer(client, phone="0812345678", pin="2468", **extra):
    data = {"csrf_token": form_csrf(client, "/order/register"), "phone": phone, "pin": pin, "pin_confirm": pin}
    data.update(extra)
    return client.post("/order/register", data=data)


def login_customer(client, phone="0812345678", pin="2468"):
    return client.post("/order/login", data={
        "csrf_token": form_csrf(client, "/order/login"), "phone": phone, "pin": pin, "action": "login",
    })
