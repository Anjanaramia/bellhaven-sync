"""
Thin wrapper around the CRM sandbox API. Every network call to the CRM
lives here and nowhere else — the matcher, validator, and review app
never call `requests` directly. This is the seam to touch if a live-demo
request changes how we read or write accounts.
"""
import requests
from . import config


class CRMClient:
    def __init__(self, base_url=None, token=None):
        self.base_url = base_url or config.CRM_BASE_URL
        self.token = token or config.CRM_TOKEN
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})

    def list_accounts(self, q: str | None = None, page_size: int = 50) -> list[dict]:
        """
        Fetch all accounts, following the CONFIRMED pagination shape:
        query params page/page_size, response wrapper {"data": [...],
        "page": N, "page_size": N, "total": N}. Loops until every page
        is collected.
        """
        results = []
        page = 1
        while True:
            params = {"page": page, "page_size": page_size}
            if q:
                params["q"] = q
            resp = self.session.get(self.base_url + config.ENDPOINTS["list_accounts"], params=params)
            resp.raise_for_status()
            data = resp.json()

            results.extend(data.get("data", []))
            total = data.get("total", len(results))
            if len(results) >= total or not data.get("data"):
                break
            page += 1

        return results

    def get_account(self, account_id: str) -> dict:
        url = self.base_url + config.ENDPOINTS["get_account"].format(id=account_id)
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def create_account(self, payload: dict) -> dict:
        url = self.base_url + config.ENDPOINTS["create_account"]
        resp = self.session.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def update_account(self, account_id: str, payload: dict) -> dict:
        url = self.base_url + config.ENDPOINTS["update_account"].format(id=account_id)
        resp = self.session.patch(url, json=payload)
        resp.raise_for_status()
        return resp.json()
