from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _auth_headers(client: TestClient, email: str = 'liquid@test.com', country: str = 'United Kingdom') -> dict[str, str]:
    register = client.post(
        '/auth/register',
        json={
            'name': 'Liquid Tester',
            'email': email,
            'password': 'StrongPass123',
            'country': country,
        },
    )
    assert register.status_code == 201, register.text

    login = client.post(
        '/auth/login',
        json={
            'email': email,
            'password': 'StrongPass123',
        },
    )
    assert login.status_code == 200, login.text

    token = login.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def test_liquid_intake_list_is_paginated(client: TestClient) -> None:
    headers = _auth_headers(client)

    for idx in range(3):
        response = client.post(
            '/wellness/water/',
            headers=headers,
            json={
                'liquid_type': 'water',
                'drink_type': 'water',
                'amount_ml': 250 + idx,
                'is_alcoholic': False,
            },
        )
        assert response.status_code == 201, response.text

    page_1 = client.get('/wellness/liquid-intake/?page=1&page_size=2', headers=headers)
    assert page_1.status_code == 200, page_1.text
    payload_1 = page_1.json()

    assert payload_1['total'] == 3
    assert payload_1['page'] == 1
    assert payload_1['page_size'] == 2
    assert payload_1['total_pages'] == 2
    assert len(payload_1['items']) == 2

    page_2 = client.get('/wellness/liquid-intake/?page=2&page_size=2', headers=headers)
    assert page_2.status_code == 200, page_2.text
    payload_2 = page_2.json()

    assert payload_2['page'] == 2
    assert len(payload_2['items']) == 1


def test_weekly_summary_uses_country_specific_limit(client: TestClient) -> None:
    headers = _auth_headers(client, email='germany@test.com', country='Germany')

    now = datetime.now(timezone.utc)
    in_week = now - timedelta(days=1)

    entries = [
        {'liquid_type': 'beer', 'drink_type': 'beer', 'amount_ml': 500, 'is_alcoholic': True, 'abv': 5.0, 'logged_at': in_week.isoformat()},
        {'liquid_type': 'wine', 'drink_type': 'wine', 'amount_ml': 175, 'is_alcoholic': True, 'abv': 12.0, 'logged_at': in_week.isoformat()},
    ]

    for payload in entries:
        response = client.post('/wellness/water/', headers=headers, json=payload)
        assert response.status_code == 201, response.text

    summary = client.get('/wellness/liquid-intake/weekly-summary', headers=headers)
    assert summary.status_code == 200, summary.text
    data = summary.json()

    expected_units = (500 * 5.0) / 1000 + (175 * 12.0) / 1000

    assert data['country'] == 'Germany'
    assert data['weekly_limit_units'] == 12.0
    assert abs(data['weekly_units'] - expected_units) < 0.001
    assert abs(data['percentage_of_limit'] - ((expected_units / 12.0) * 100)) < 0.001
