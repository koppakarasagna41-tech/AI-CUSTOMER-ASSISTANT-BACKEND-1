import random
import string
import sys
import httpx

base = 'http://127.0.0.1:8000'
api_base = base + '/api/v1'

ADMIN_EMAIL = 'koppakarasagna41@gmail.com'
ADMIN_PASSWORD = 'rasagna@A3'

client = httpx.Client(timeout=30.0)
results = []


def record(name, success, payload):
    results.append({'name': name, 'status': 'PASS' if success else 'FAIL', 'payload': payload})


def check(name, func):
    try:
        payload = func()
        print('PASS', name)
        record(name, True, payload)
    except Exception as exc:
        message = str(exc)
        print('FAIL', name, message)
        record(name, False, message)


def admin_login():
    r = client.post(api_base + '/auth/login', json={'email': ADMIN_EMAIL, 'password': ADMIN_PASSWORD})
    r.raise_for_status()
    d = r.json()
    return d


def auth_me(token):
    r = client.get(api_base + '/auth/me', headers={'Authorization': f'Bearer {token}'})
    r.raise_for_status()
    return r.json()


def auth_refresh(refresh_token):
    r = client.post(api_base + '/auth/refresh', json={'refresh_token': refresh_token})
    r.raise_for_status()
    return r.json()


def register_customer():
    email = 'testuser+' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6)) + '@example.com'
    r = client.post(api_base + '/auth/register', json={
        'full_name': 'Runtime Test User',
        'email': email,
        'password': 'CustomerPass123!'
    })
    r.raise_for_status()
    result = r.json()
    return {'email': email, 'result': result}


def customer_login(email):
    r = client.post(api_base + '/auth/login', json={'email': email, 'password': 'CustomerPass123!'})
    r.raise_for_status()
    return r.json()


def ticket_categories(token):
    r = client.get(api_base + '/tickets/categories', headers={'Authorization': f'Bearer {token}'})
    r.raise_for_status()
    return r.json()


def create_ticket(token):
    r = client.post(api_base + '/tickets', json={
        'subject': 'Runtime verification ticket',
        'description': 'Ticket created during runtime verification.',
        'category': 'billing'
    }, headers={'Authorization': f'Bearer {token}'})
    r.raise_for_status()
    return r.json()


def list_tickets(token):
    r = client.get(api_base + '/tickets', headers={'Authorization': f'Bearer {token}'})
    r.raise_for_status()
    return r.json()


def rag_ask(token):
    r = client.post(api_base + '/rag/ask', json={'question': 'How do I reset my password?'}, headers={'Authorization': f'Bearer {token}'})
    r.raise_for_status()
    return r.json()


def chat_start(token):
    r = client.post(api_base + '/chat', json={'message': 'Hello, I need help with billing.'}, headers={'Authorization': f'Bearer {token}'})
    r.raise_for_status()
    return r.json()


if __name__ == '__main__':
    check('health', lambda: client.get(base + '/health').json())
    admin_login_result = None
    try:
        admin_login_result = admin_login()
        admin_token = admin_login_result['data']['tokens']['access_token']
        admin_refresh = admin_login_result['data']['tokens']['refresh_token']
    except Exception as exc:
        pass

    if admin_login_result:
        check('auth_me', lambda: auth_me(admin_token))
        check('auth_refresh', lambda: auth_refresh(admin_refresh))
        check('admin_users_list', lambda: client.get(api_base + '/users', headers={'Authorization': f'Bearer {admin_token}'}).json())
        check('admin_create_agent', lambda: client.post(api_base + '/admin/agents', json={
            'full_name': 'Runtime Agent',
            'email': 'agent+' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6)) + '@example.com',
            'password': 'AgentPass123!',
            'role': 'agent'
        }, headers={'Authorization': f'Bearer {admin_token}'}).json())

    customer = None
    check('register_customer', register_customer)
    try:
        customer = register_customer()
        customer_token = customer['result']['data']['tokens']['access_token']
    except Exception:
        customer = None
        customer_token = None

    if customer_token:
        check('customer_login', lambda: customer_login(customer['email']))
        check('ticket_categories', lambda: ticket_categories(customer_token))
        check('create_ticket', lambda: create_ticket(customer_token))
        check('list_tickets', lambda: list_tickets(customer_token))
        check('rag_ask', lambda: rag_ask(customer_token))
        check('chat_start', lambda: chat_start(customer_token))

    print('\nFINAL RESULTS:')
    for item in results:
        print(f"{item['name']}: {item['status']}")
    sys.exit(0)
