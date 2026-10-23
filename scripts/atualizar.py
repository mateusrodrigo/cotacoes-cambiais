
"""Centraliza a cotação USD/BRL comercial e PTAX, com histórico incremental."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE_API = "https://economia.awesomeapi.com.br"
API_ATUAL = f"{BASE_API}/json/last/USD-BRL,USD-BRLPTAX"
API_HISTORICO = {
    "comercial": f"{BASE_API}/json/daily/USD-BRL/30",
    "ptax": f"{BASE_API}/json/daily/USD-BRLPTAX/30",
}
PASTA = Path(__file__).resolve().parents[1] / "docs"
FUSO = ZoneInfo("America/Fortaleza")


def consultar(url, chave):
    requisicao = Request(
        url,
        headers={
            "User-Agent": "CotacoesCambiais/2.0",
            "x-api-key": chave,
            "Accept": "application/json",
        },
    )
    for tentativa in range(3):
        try:
            with urlopen(requisicao, timeout=30) as resposta:
                return json.load(resposta)
        except HTTPError as erro:
            if erro.code not in (429, 500, 502, 503, 504) or tentativa == 2:
                raise
        except (URLError, TimeoutError):
            if tentativa == 2:
                raise
        time.sleep(2 ** (tentativa + 1))
    raise RuntimeError(f"Falha na consulta: {url}")


def normalizar(item):
    timestamp = int(item["timestamp"])
    if timestamp > 10**11:  # Registros antigos podem usar milissegundos.
        timestamp //= 1000
    instante = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(FUSO)
    compra, venda = float(item["bid"]), float(item["ask"])
    if compra <= 0 or venda <= 0:
        raise ValueError("Cotação de compra/venda inválida.")

    registro = {
        "data": instante.date().isoformat(),
        "data_hora": instante.isoformat(timespec="seconds"),
        "timestamp": timestamp,
        "compra": compra,
        "venda": venda,
    }
    campos_opcionais = {
        "high": "maxima",
        "low": "minima",
        "varBid": "variacao",
        "pctChange": "variacao_percentual",
    }
    for origem, destino in campos_opcionais.items():
        if item.get(origem) not in (None, ""):
            registro[destino] = float(item[origem])
        elif item.get(destino) not in (None, ""):
            registro[destino] = float(item[destino])
    return registro


def registrar(registros, itens):
    por_data = {registro["data"]: registro for registro in registros}
    for item in itens:
        registro = normalizar(item) if "bid" in item else item
        anterior = por_data.get(registro["data"])
        if anterior is None or registro["timestamp"] >= anterior["timestamp"]:
            por_data[registro["data"]] = registro
    return [por_data[data] for data in sorted(por_data)]


def carregar_historico():
    arquivo = PASTA / "historico.json"
    if not arquivo.exists():
        return {"comercial": [], "ptax": []}
    conteudo = json.loads(arquivo.read_text(encoding="utf-8"))
    if isinstance(conteudo, list):  # Migra automaticamente o histórico antigo.
        conteudo = {"comercial": conteudo, "ptax": []}
    if not isinstance(conteudo, dict):
        raise ValueError("Formato inválido em historico.json")

    historico = {}
    for tipo in ("comercial", "ptax"):
        registros = conteudo.get(tipo, [])
        if not isinstance(registros, list):
            raise ValueError(f"Histórico {tipo} inválido.")
        historico[tipo] = registrar([], registros)
    return historico


def gravar(nome, conteudo):
    destino = PASTA / nome
    temporario = destino.with_suffix(".json.tmp")
    temporario.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporario.replace(destino)


def atualizar():
    chave = os.environ.get("AWESOME_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("Configure o secret AWESOME_API_KEY no GitHub Actions.")

    ultimas = consultar(API_ATUAL, chave)
    if not isinstance(ultimas, dict) or not all(
        codigo in ultimas for codigo in ("USDBRL", "USDBRLPTAX")
    ):
        raise ValueError("A API não retornou USD-BRL e USD-BRLPTAX.")

    diarios = {}
    for tipo, url in API_HISTORICO.items():
        try:
            diarios[tipo] = consultar(url, chave)
        except HTTPError as erro:
            if tipo != "ptax" or erro.code != 404:
                raise
            print("Aviso: histórico PTAX indisponível; será acumulado diariamente.")
            diarios[tipo] = []
        if not isinstance(diarios[tipo], list):
            raise ValueError(f"A API retornou um histórico {tipo} inválido.")

    PASTA.mkdir(parents=True, exist_ok=True)
    historico = carregar_historico()
    codigos = {"comercial": "USDBRL", "ptax": "USDBRLPTAX"}
    for tipo, codigo in codigos.items():
        historico[tipo] = registrar(
            historico[tipo], [*diarios[tipo], ultimas[codigo]]
        )
        if not historico[tipo]:
            raise ValueError(f"Nenhuma cotação {tipo} disponível.")

    coletado_em = datetime.now(FUSO).isoformat(timespec="seconds")
    cotacoes = {
        "par": "USD/BRL",
        "coletado_em": coletado_em,
        "fontes": {
            "comercial": "AwesomeAPI",
            "ptax": "Banco Central do Brasil via AwesomeAPI",
        },
        "comercial": historico["comercial"][-1],
        "ptax": historico["ptax"][-1],
    }
    gravar("cotacao.json", cotacoes)
    gravar("historico.json", {"par": "USD/BRL", **historico})

    for tipo in ("comercial", "ptax"):
        atual = cotacoes[tipo]
        print(
            f"{tipo.upper()}: {atual['data']} | "
            f"compra R$ {atual['compra']:.4f} | "
            f"venda R$ {atual['venda']:.4f} | "
            f"{len(historico[tipo])} dias registrados"
        )


if __name__ == "__main__":
    atualizar()
