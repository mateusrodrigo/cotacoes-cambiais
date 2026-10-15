"""Atualiza cotação e histórico USD/BRL para publicação estática."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API = "https://economia.awesomeapi.com.br/json/daily/USD-BRL/30"
BASE = Path(__file__).resolve().parents[1]
PASTA = BASE / "docs"
FUSO = ZoneInfo("America/Fortaleza")


def consultar():
    chave = os.environ.get("AWESOME_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("Configure o secret AWESOME_API_KEY no GitHub Actions.")

    requisicao = Request(
        API,
        headers={
            "User-Agent": "CotacoesCambiais/1.0",
            "x-api-key": chave,
            "Accept": "application/json",
        },
    )
    for tentativa in range(3):
        try:
            with urlopen(requisicao, timeout=30) as resposta:
                dados = json.load(resposta)
            if not isinstance(dados, list) or not dados:
                raise ValueError("A API não retornou uma lista de cotações.")
            return dados
        except HTTPError as erro:
            if erro.code not in (429, 500, 502, 503, 504) or tentativa == 2:
                raise
        except URLError:
            if tentativa == 2:
                raise
        time.sleep(2 ** (tentativa + 1))
    raise RuntimeError("Não foi possível consultar a API.")


def atualizar(dados):
    PASTA.mkdir(parents=True, exist_ok=True)
    destino_historico = PASTA / "historico.json"
    if destino_historico.exists():
        historico = json.loads(destino_historico.read_text(encoding="utf-8"))
        if not isinstance(historico, list):
            raise ValueError("O histórico existente não é uma lista JSON.")
    else:
        historico = []

    registros = {item["data"]: item for item in historico}
    for item in dados:
        instante = datetime.fromtimestamp(
            int(item["timestamp"]), tz=timezone.utc
        ).astimezone(FUSO)
        data = instante.date().isoformat()
        registro = {
            "data": data,
            "timestamp": int(item["timestamp"]),
            "bid": float(item["bid"]),
            "ask": float(item["ask"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "varBid": float(item["varBid"]),
            "pctChange": float(item["pctChange"]),
        }
        anterior = registros.get(data)
        if anterior is None or registro["timestamp"] >= int(anterior["timestamp"]):
            registros[data] = registro

    if not registros:
        raise ValueError("Nenhuma cotação válida disponível.")

    historico_ordenado = [registros[d] for d in sorted(registros)]
    atual = historico_ordenado[-1]
    for nome, conteudo in (("historico.json", historico_ordenado), ("cotacao.json", atual)):
        (PASTA / nome).write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Cotação mais recente: {atual['data']} | USD/BRL: {atual['bid']}")
    print(f"Dias registrados: {len(historico_ordenado)}")


if __name__ == "__main__":
    atualizar(consultar())
