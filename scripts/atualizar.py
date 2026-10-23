"""Publica USD/BRL indicativo (AwesomeAPI) e PTAX de fechamento (BCB SGS).

Não usa cotação PTAX intradiária. A série do SGS (10813/1) representa
exclusivamente as taxas diárias de fechamento de compra e venda.
"""

import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_COMERCIAL = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
API_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
SERIES_PTAX = {"compra": 10813, "venda": 1}
DIAS_RETROATIVOS = 120
PASTA = Path(__file__).resolve().parents[1] / "docs"
FUSO = ZoneInfo("America/Fortaleza")


def consultar_json(url, chave=None):
    headers = {
        "User-Agent": "CotacoesCambiais/3.1",
        "Accept": "application/json",
    }
    if chave:
        headers["x-api-key"] = chave

    for tentativa in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as resposta:
                return json.load(resposta)
        except HTTPError as erro:
            if erro.code not in (408, 429, 500, 502, 503, 504) or tentativa == 2:
                raise
            print(f"Aviso: HTTP {erro.code}; repetindo a consulta ({tentativa + 1}/3).")
        except (URLError, TimeoutError) as erro:
            if tentativa == 2:
                raise
            print(f"Aviso: erro de conexão; repetindo a consulta ({tentativa + 1}/3): {erro}")
        time.sleep(2 ** (tentativa + 1))
    raise RuntimeError("Falha inesperada de conexão.")


def numero(valor):
    resultado = float(valor)
    if not math.isfinite(resultado):
        raise ValueError("Valor numérico não finito recebido.")
    return resultado


def normalizar_comercial(item):
    ts = int(item["timestamp"])
    if ts > 10**11:
        ts //= 1000
    instante = datetime.fromtimestamp(ts, timezone.utc).astimezone(FUSO)
    compra = numero(item.get("bid", item.get("compra")))
    venda = numero(item.get("ask", item.get("venda")))
    if compra <= 0 or venda <= 0:
        raise ValueError("Cotação comercial inválida.")

    registro = {
        "data": instante.date().isoformat(),
        "data_hora": instante.isoformat(timespec="seconds"),
        "timestamp": ts,
        "compra": compra,
        "venda": venda,
        "fonte": "AwesomeAPI",
        "tipo": "mercado_indicativo",
    }
    for original, campo in (
        ("high", "maxima"),
        ("low", "minima"),
        ("varBid", "variacao"),
        ("pctChange", "variacao_percentual"),
    ):
        valor = item.get(original, item.get(campo))
        if valor not in (None, ""):
            registro[campo] = numero(valor)
    return registro


def carregar_historico():
    destino = PASTA / "historico.json"
    if not destino.exists():
        return {"comercial": [], "ptax": []}
    conteudo = json.loads(destino.read_text(encoding="utf-8"))
    if isinstance(conteudo, list):
        conteudo = {"comercial": conteudo, "ptax": []}
    if not isinstance(conteudo, dict):
        raise ValueError("O histórico existente possui formato inválido.")

    comercial = conteudo.get("comercial", [])
    ptax = conteudo.get("ptax", [])
    if not isinstance(comercial, list) or not isinstance(ptax, list):
        raise ValueError("As duas séries históricas precisam ser listas.")

    # Não confundir registros PTAX antigos da AwesomeAPI com fechamentos oficiais.
    ptax_confiavel = [
        registro for registro in ptax
        if isinstance(registro, dict)
        and registro.get("confirmada") is True
        and registro.get("tipo_boletim") == "Fechamento"
        and registro.get("fonte") == "Banco Central do Brasil"
        and isinstance(registro.get("data"), str)
    ]
    return {
        "comercial": [normalizar_comercial(item) for item in comercial],
        "ptax": ptax_confiavel,
    }


def obter_comercial(chave):
    resposta = consultar_json(API_COMERCIAL, chave)
    if not isinstance(resposta, dict) or not isinstance(resposta.get("USDBRL"), dict):
        raise ValueError("Resposta sem a cotação comercial USDBRL.")
    return normalizar_comercial(resposta["USDBRL"])


def consultar_serie(codigo, inicio, fim):
    parametros = urlencode({
        "formato": "json",
        "dataInicial": inicio.strftime("%d/%m/%Y"),
        "dataFinal": fim.strftime("%d/%m/%Y"),
    })
    url = f"{API_SGS.format(codigo=codigo)}?{parametros}"
    try:
        resposta = consultar_json(url)
    except (HTTPError, URLError, TimeoutError) as erro:
        print(f"Aviso: série SGS {codigo} por período indisponível ({erro}). Tentando últimos 20 registros.")
        url_alternativa = f"{API_SGS.format(codigo=codigo)}/ultimos/20?formato=json"
        resposta = consultar_json(url_alternativa)
    if not isinstance(resposta, list):
        raise ValueError(f"BCB SGS {codigo}: retorno não é uma lista JSON.")
    pontos = {}
    for item in resposta:
        dia = datetime.strptime(item["data"], "%d/%m/%Y").date()
        taxa = numero(item["valor"])
        if taxa <= 0:
            raise ValueError(f"BCB SGS {codigo}: cotação não positiva.")
        if dia <= fim:
            pontos[dia.isoformat()] = taxa
    return pontos


def obter_ptax(inicio, fim):
    compra = consultar_serie(SERIES_PTAX["compra"], inicio, fim)
    venda = consultar_serie(SERIES_PTAX["venda"], inicio, fim)
    comuns = sorted(compra.keys() & venda.keys())
    if not comuns:
        raise ValueError("BCB não retornou datas coincidentes de compra e venda da PTAX.")
    if max(compra) != max(venda):
        print("Aviso: séries SGS com datas máximas diferentes; apenas datas pareadas serão publicadas.")

    registros = []
    for dia in comuns:
        registros.append({
            "data": dia,
            # SGS informa apenas a data do fechamento, não seu horário.
            "compra": compra[dia],
            "venda": venda[dia],
            "fonte": "Banco Central do Brasil",
            "tipo_boletim": "Fechamento",
            "confirmada": True,
            "series_sgs": {"compra": 10813, "venda": 1},
        })
    return registros


def consolidar_comercial(registros):
    por_data = {}
    for item in registros:
        registro = normalizar_comercial(item)
        dia = registro["data"]
        atual = por_data.get(dia)
        if atual is None or registro["timestamp"] >= atual["timestamp"]:
            por_data[dia] = registro
    return [por_data[dia] for dia in sorted(por_data)]


def consolidar_ptax(registros):
    # Último registro prevalece: valores oficiais recuperados do SGS podem
    # corrigir cotações anteriores para uma mesma data.
    por_data = {item["data"]: dict(item) for item in registros}
    serie = [por_data[dia] for dia in sorted(por_data)]
    for indice, item in enumerate(serie):
        item.pop("variacao", None)
        item.pop("variacao_percentual", None)
        if indice:
            anterior = serie[indice - 1]["compra"]
            diferenca = item["compra"] - anterior
            item["variacao"] = round(diferenca, 6)
            item["variacao_percentual"] = round(diferenca / anterior * 100, 6)
    return serie


def gravar(nome, dados):
    arquivo = PASTA / nome
    temporario = arquivo.with_suffix(".json.tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporario.replace(arquivo)


def atualizar():
    chave = os.environ.get("AWESOME_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("Configure o secret AWESOME_API_KEY no GitHub Actions.")

    agora = datetime.now(FUSO)
    PASTA.mkdir(parents=True, exist_ok=True)
    anterior = carregar_historico()
    comercial_novo = obter_comercial(chave)
    comercial = consolidar_comercial([*anterior["comercial"], comercial_novo])

    consulta_ptax_ok = False
    try:
        dados_ptax = obter_ptax(agora.date() - timedelta(days=DIAS_RETROATIVOS), agora.date())
        consulta_ptax_ok = True
    except (HTTPError, URLError, TimeoutError) as erro:
        if not anterior["ptax"]:
            raise RuntimeError("Banco Central indisponível e sem histórico PTAX oficial validado para reutilizar.") from erro
        dados_ptax = []
        print(f"Aviso: BCB temporariamente indisponível. PTAX oficial anterior preservada: {erro}")

    ptax = consolidar_ptax([*anterior["ptax"], *dados_ptax])
    if not ptax:
        raise RuntimeError("Nenhuma PTAX de fechamento confirmada disponível.")
    if date.fromisoformat(ptax[-1]["data"]) > agora.date():
        raise ValueError("BCB retornou PTAX com data futura.")

    saida = {
        "par": "USD/BRL",
        "coletado_em": datetime.now(FUSO).isoformat(timespec="seconds"),
        "fontes": {"comercial": "AwesomeAPI", "ptax": "Banco Central do Brasil"},
        "ptax_consulta_atualizada": consulta_ptax_ok,
        "comercial": comercial[-1],
        "ptax": ptax[-1],
    }
    gravar("historico.json", {"par": "USD/BRL", "comercial": comercial, "ptax": ptax})
    gravar("cotacao.json", saida)

    print("=== COTAÇÕES CAMBIAIS ATUALIZADAS ===")
    print(f"Coleta: {saida['coletado_em']}")
    print(f"Comercial: {comercial[-1]['data']} | compra R$ {comercial[-1]['compra']:.4f} | {len(comercial)} datas")
    print(f"PTAX SGS: {ptax[-1]['data']} | compra R$ {ptax[-1]['compra']:.4f} | {len(ptax)} datas")
    if not consulta_ptax_ok:
        print("Atenção: nesta execução, foi reutilizado o último fechamento oficial já confirmado.")
    elif ptax[-1]["data"] < agora.date().isoformat():
        print("Atenção: fechamento PTAX mais recente anterior a hoje (feriado, fim de semana ou publicação pendente).")


if __name__ == "__main__":
    atualizar()
