
"""Centraliza cotações USD/BRL comercial e PTAX, com histórico incremental."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE_API = "https://economia.awesomeapi.com.br"

API_ATUAL = {
    "comercial": f"{BASE_API}/json/last/USD-BRL",
    "ptax": f"{BASE_API}/json/last/USD-BRLPTAX",
}

API_HISTORICO = {
    "comercial": f"{BASE_API}/json/daily/USD-BRL/30",
    "ptax": f"{BASE_API}/json/daily/USD-BRLPTAX/30",
}

CODIGOS = {
    "comercial": "USDBRL",
    "ptax": "USDBRLPTAX",
}

PASTA = Path(__file__).resolve().parents[1] / "docs"
FUSO = ZoneInfo("America/Fortaleza")


def consultar(url, chave):
    requisicao = Request(
        url,
        headers={
            "User-Agent": "CotacoesCambiais/2.1",
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

    if timestamp > 10**11:
        timestamp //= 1000

    instante = datetime.fromtimestamp(
        timestamp, tz=timezone.utc
    ).astimezone(FUSO)

    compra = float(item["bid"])
    venda = float(item["ask"])

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
        valor = item.get(origem)

        if valor in (None, ""):
            valor = item.get(destino)

        if valor not in (None, ""):
            registro[destino] = float(valor)

    return registro


def registrar(registros, itens):
    por_data = {}

    for item in [*registros, *itens]:
        registro = normalizar(item) if "bid" in item else item

        data = registro["data"]
        timestamp = int(registro["timestamp"])

        anterior = por_data.get(data)

        if anterior is None or timestamp >= int(anterior["timestamp"]):
            por_data[data] = registro

    return [por_data[data] for data in sorted(por_data)]


def carregar_historico():
    arquivo = PASTA / "historico.json"

    if not arquivo.exists():
        return {"comercial": [], "ptax": []}

    conteudo = json.loads(arquivo.read_text(encoding="utf-8"))

    # Migração automática do formato antigo.
    if isinstance(conteudo, list):
        conteudo = {
            "comercial": conteudo,
            "ptax": [],
        }

    if not isinstance(conteudo, dict):
        raise ValueError("Formato inválido em historico.json.")

    historico = {}

    for tipo in CODIGOS:
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
        raise RuntimeError(
            "Configure o secret AWESOME_API_KEY no GitHub Actions."
        )

    # Consultas individuais das últimas cotações.
    ultimas = {}

    for tipo, url in API_ATUAL.items():
        resposta = consultar(url, chave)
        codigo = CODIGOS[tipo]

        if not isinstance(resposta, dict) or codigo not in resposta:
            raise ValueError(
                f"A API não retornou a cotação {tipo} ({codigo})."
            )

        ultimas[tipo] = resposta[codigo]

        print(
            f"Consulta {tipo}: "
            f"{ultimas[tipo].get('create_date', 'sem data')}"
        )

    # Histórico dos últimos 30 registros de cada modalidade.
    diarios = {}

    for tipo, url in API_HISTORICO.items():
        try:
            diarios[tipo] = consultar(url, chave)

        except HTTPError as erro:
            if tipo != "ptax" or erro.code != 404:
                raise

            print(
                "Aviso: histórico PTAX indisponível. "
                "Os registros serão acumulados diariamente."
            )

            diarios[tipo] = []

        if not isinstance(diarios[tipo], list):
            raise ValueError(
                f"A API retornou um histórico {tipo} inválido."
            )

    # Carregamento e atualização incremental.
    PASTA.mkdir(parents=True, exist_ok=True)

    historico = carregar_historico()

    for tipo in CODIGOS:
        historico[tipo] = registrar(
            historico[tipo],
            [*diarios[tipo], ultimas[tipo]],
        )

        if not historico[tipo]:
            raise ValueError(
                f"Nenhuma cotação {tipo} disponível."
            )

    # Consolidação das últimas cotações.
    coletado_em = datetime.now(FUSO).isoformat(
        timespec="seconds"
    )

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

    # Publicação dos arquivos JSON.
    gravar("cotacao.json", cotacoes)

    gravar(
        "historico.json",
        {
            "par": "USD/BRL",
            **historico,
        },
    )

    # Relatório de execução.
    print("\n=== COTAÇÕES CAMBIAIS ATUALIZADAS ===")
    print(f"Coleta: {coletado_em}")

    for tipo in CODIGOS:
        atual = cotacoes[tipo]

        print(f"\n{tipo.upper()}")
        print(f"Data: {atual['data']}")
        print(f"Horário: {atual['data_hora']}")
        print(f"Compra: R$ {atual['compra']:.4f}")
        print(f"Venda: R$ {atual['venda']:.4f}")
        print(f"Registros históricos: {len(historico[tipo])}")

    print("\nArquivos atualizados:")
    print("- docs/cotacao.json")
    print("- docs/historico.json")


if __name__ == "__main__":
    atualizar()
