from __future__ import annotations

import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BASE_URL = "https://api.cartolafc.globo.com"

class CartolaClient:
    """
    Cliente HTTP com retry/backoff para endpoints do Cartola FC.
    A API não é oficialmente documentada e pode variar. Este client tenta ser robusto.
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

        retry = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def mercado_status(self) -> dict:
        return self._get("/mercado/status")

    def atletas_mercado(self) -> dict:
        return self._get("/atletas/mercado")

    def partidas(self) -> dict:
        return self._get("/partidas")

    def clubes(self) -> dict:
        return self._get("/clubes")

    def rodadas(self) -> dict:
        return self._get("/rodadas")

    def parciais(self) -> dict:
        """
        Parciais/pontuados em "tempo real" durante jogos/rodada.
        Pode falhar dependendo do status do mercado/rodada.
        """
        return self._get("/atletas/pontuados")
