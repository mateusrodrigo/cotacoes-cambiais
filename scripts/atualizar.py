"""Publica USD/BRL de mercado (AwesomeAPI) e PTAX de fechamento (BCB)."""

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_COMERCIAL = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
API_PTAX = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoMoedaPeriodoFechamento(codigoMoeda=@codigoMoeda,"
    "dataInicialCotacao=@dataInicialCotacao,dataFinalCotacao=@dataFinalCotacao)"
)
BASE = Path(__file__).resolve().parents[1]
PASTA = BASE / "docs"
FUSO = ZoneInfo("America/Fortaleza")
FUSO_BCB = ZoneInfo("America/Sao_Paulo")
DIAS_PTAX_INICIAIS = 120


def consultar_json(url, chave=None):
    cabecalhos = {
        "User-Agent": "CotacoesCambiais/3.0 (GitHub Actions)",
        "Accept": "application/json",
    }
    if chave:
        cabecalhos["x-api-key"] = chave

    for tentativa in range(3):
        try:
            requisicao = Request(url, headers=cabecalhos)
            with urlopen(requisicao, timeout=30) as resposta:
                return json.load(resposta)
        except HTTPError as erro:
            if erro.code not in (429, 500, 502, 503, 504) or tentativa == 2:
                raise
        except (URLError, TimeoutError):
            if tentativa == 2:
                raise
        time.sleep(2 ** (tentativa + 1))

    raise RuntimeError("Não foi possível consultar a fonte.")


def numero(valor):
    resultado = float(valor)
    if not math.isfinite(resultado):
        raise ValueError("A fonte retornou um número não finito.")
    return resultado


def hora_fortaleza(timestamp):
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).astimezone(FUSO)


def normalizar_comercial(item):
    """Aceita o JSON da AwesomeAPI e registros antigos do projeto."""
    ts = int(item["timestamp"])
    if ts > 10**11:
        ts //= 1000
    instante = hora_fortaleza(ts)
    compra = numero(item.get("bid", item.get("compra")))
    venda = numero(item.get("ask", item.get("venda")))
    if compra <= 0 or venda <= 0:
        raise ValueError("Compra/venda comercial inválida.")

    registro = {
        "data": instante.date().isoformat(),
        "data_hora": instante.isoformat(timespec="seconds"),
        "timestamp": ts,
        "compra": compra,
        "venda": venda,
        "fonte": "AwesomeAPI",
        "tipo": "mercado_indicativo",
    }
    for origem, destino in (
        ("high", "maxima"),
        ("low", "minima"),
        ("varBid", "variacao"),
        ("pctChange", "variacao_percentual"),
    ):
        valor = item.get(origem, item.get(destino))
        if valor is not None and valor != "":
            registro[destino] = numero(valor)
    return registro


def normalizar_ptax(item):
    """Somente boletins de fechamento devolvidos pela API oficial do BCB."""
    tipo = str(item.get("tipoBoletim", "")).strip().casefold()
    if tipo not in ("fechamento", "fechamento ptax"):
        raise ValueError(f"Boletim inesperado no endpoint de fechamento: {tipo!r}")

    valor_data = str(item["dataHoraCotacao"])
    instante = datetime.fromisoformat(valor_data.replace(" ", "T"))
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=FUSO_BCB)
    instante = instante.astimezone(FUSO)
    compra = numero(item["cotacaoCompra"])
    venda = numero(item["cotacaoVenda"])
    if compra <= 0 or venda <= 0:
        raise ValueError("PTAX oficial inválida.")

    return {
        "data": instante.date().isoformat(),
        "data_hora": instante.isoformat(timespec="seconds"),
        "timestamp": int(instante.timestamp()),
        "compra": compra,
        "venda": venda,
        "fonte": "Banco Central do Brasil",
        "tipo_boletim": "Fechamento",
        "confirmada": True,
    }


def carregar_historico():
    arquivo = PASTA / "historico.json"
    if not arquivo.exists():
        return {"comercial": [], "ptax": []}
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    if isinstance(dados, list):
        dados = {"comercial": dados, "ptax": []}
    if not isinstance(dados, dict):
        raise ValueError("historico.json precisa ser um objeto ou lista antiga.")

    comercial = dados.get("comercial", [])
    ptax = dados.get("ptax", [])
    if not isinstance(comercial, list) or not isinstance(ptax, list):
        raise ValueError("As séries em historico.json devem ser listas.")

    # PTAX antiga da AwesomeAPI não é classificada como BCB confirmado.
    ptax_confirmada = [
        r for r in ptax
        if isinstance(r, dict)
        and r.get("confirmada") is True
        and r.get("fonte") == "Banco Central do Brasil"
        and r.get("tipo_boletim") == "Fechamento"
    ]
    return {
        "comercial": [normalizar_comercial(r) for r in comercial],
        "ptax": ptax_confirmada,
    }


def consolidar(registros):
    por_data = {}
    for registro in registros:
        dia = registro["data"]
        anterior = por_data.get(dia)
        if anterior is None or int(registro["timestamp"]) >= int(anterior["timestamp"]):
            por_data[dia] = registro
    return [por_data[dia] for dia in sorted(por_data)]


def obter_comercial(chave):
    dados = consultar_json(API_COMERCIAL, chave)
    if not isinstance(dados, dict) or not isinstance(dados.get("USDBRL"), dict):
        raise ValueError("A AwesomeAPI não retornou a chave USDBRL.")
    return normalizar_comercial(dados["USDBRL"])


def obter_ptax(periodo_inicio, periodo_fim):
    parametros = urlencode({
        "@codigoMoeda": "'USD'",
        "@dataInicialCotacao": f"'{periodo_inicio:%m-%d-%Y}'",
        "@dataFinalCotacao": f"'{periodo_fim:%m-%d-%Y}'",
        "$format": "json",
        "$top": "1000",
    })
    dados = consultar_json(f"{API_PTAX}?{parametros}")
    if not isinstance(dados, dict) or not isinstance(dados.get("value"), list):
        raise ValueError("O BCB não retornou a lista 'value' esperada.")
    if "@odata.nextLink" in dados:
        raise RuntimeError("Resposta PTAX paginada: amplie a rotina antes de publicar dados incompletos.")
    registros = [normalizar_ptax(r) for r in dados["value"]]
    if not registros:
        raise RuntimeError("Nenhum fechamento PTAX retornado pelo BCB no período consultado.")
    return registros


def incluir_variacoes_ptax(registros):
    for indice, item in enumerate(registros):
        if indice == 0:
            item.pop("variacao", None)
            item.pop("variacao_percentual", None)
            continue
        anterior = registros[indice - 1]["compra"]
        diferenca = item["compra"] - anterior
        item["variacao"] = round(diferenca, 6)
        item["variacao_percentual"] = round(diferenca / anterior * 100, 6)


def gravar(nome, conteudo):
    destino = PASTA / nome
    temporario = destino.with_suffix(".json.tmp")
    temporario.write_text(
        json.dumps(conteudo, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporario.replace(destino)


def atualizar():
    chave = os.environ.get("AWESOME_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("Configure o secret AWESOME_API_KEY no GitHub Actions.")

    agora = datetime.now(FUSO)
    comercial_atual = obter_comercial(chave)
    ptax_oficial = obter_ptax(
        agora.date() - timedelta(days=DIAS_PTAX_INICIAIS), agora.date()
    )

    PASTA.mkdir(parents=True, exist_ok=True)
    anterior = carregar_historico()
    comercial = consolidar([*anterior["comercial"], comercial_atual])
    ptax = consolidar([*anterior["ptax"], *ptax_oficial])
    incluir_variacoes_ptax(ptax)

    if ptax[-1]["data"] > agora.date().isoformat():
        raise ValueError("A PTAX oficial possui data futura; publicação cancelada.")

    atual = {
        "par": "USD/BRL",
        "coletado_em": datetime.now(FUSO).isoformat(timespec="seconds"),
        "fontes": {
            "comercial": "AwesomeAPI",
            "ptax": "Banco Central do Brasil",
        },
        "comercial": comercial[-1],
        "ptax": ptax[-1],
    }
    gravar("historico.json", {"par": "USD/BRL", "comercial": comercial, "ptax": ptax})
    gravar("cotacao.json", atual)

    print("=== COTAÇÕES CAMBIAIS ATUALIZADAS ===")
    print("Coleta:", atual["coletado_em"])
    for tipo, registros in (("COMERCIAL", comercial), ("PTAX FECHAMENTO", ptax)):
        item = registros[-1]
        print(
            f"{tipo}: {item['data']} | compra R$ {item['compra']:.4f} | "
            f"venda R$ {item['venda']:.4f} | {len(registros)} dias registrados"
        )
    if ptax[-1]["data"] < agora.date().isoformat():
        print("Aviso: último fechamento PTAX é anterior a hoje (feriado, fim de semana ou publicação pendente).")


if __name__ == "__main__":
    atualizar()
