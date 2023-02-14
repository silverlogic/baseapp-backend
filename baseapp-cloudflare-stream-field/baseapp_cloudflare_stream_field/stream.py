from django.conf import settings

import requests


class StreamClient:
    @property
    def _api_url(self):
        return (
            f"https://api.cloudflare.com/client/v4/accounts/{settings.CLOUDFLARE_ACCOUNT_ID}/stream"
        )

    @property
    def _request_headers(self):
        return {"Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}"}

    def get_video_data(self, video_uid):
        res = requests.get(
            f"{self._api_url}/{video_uid}",
            headers={**self._request_headers, "Content-Type": "application/json"},
        )
        return res.json()["result"]

    def upload_via_link(self, link, meta={}):
        res = requests.post(
            f"{self._api_url}/copy",
            headers={**self._request_headers, "Content-Type": "application/json"},
            json={"url": link, "meta": meta},
        )
        return res.json()["result"]

    def update_video_data(self, video_uid, meta={}):
        res = requests.post(
            f"{self._api_url}/{video_uid}",
            headers={**self._request_headers, "Content-Type": "application/json"},
            json={"meta": meta},
        )
        return res.json()["result"]

    def delete_video_data(self, video_uid):
        res = requests.delete(
            f"{self._api_url}/{video_uid}",
            headers={**self._request_headers, "Content-Type": "application/json"},
        )
        return res.json()
