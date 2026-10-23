# Cotações Cambiais USD/BRL

Projeto de coleta, armazenamento e publicação de cotações do dólar americano em reais (USD/BRL), com atualização diária automatizada e acesso público por arquivos JSON. O objetivo é centralizar dados para consultas, análises e integração com aplicativos, incluindo ferramentas de consultoria de exportação e emissão de documentos.

O projeto utiliza **duas fontes com finalidades distintas**:

- **AwesomeAPI:** última cotação comercial indicativa de mercado disponível no momento da coleta.
- **Banco Central do Brasil (BCB):** PTAX oficial de **fechamento**, com compra, venda e histórico diário.

O processamento é feito em **Python 3.12**, a automação em **GitHub Actions** e a publicação em **GitHub Pages**.

## Página pública e arquivos JSON

**Página do projeto:** https://mateusrodrigo.github.io/cotacoes-cambiais/

| Arquivo | Conteúdo |
| --- | --- |
| [cotacao.json](https://mateusrodrigo.github.io/cotacoes-cambiais/cotacao.json) | Última observação comercial coletada e última PTAX de fechamento confirmada, cada uma com sua própria data e fonte. |
| [historico.json](https://mateusrodrigo.github.io/cotacoes-cambiais/historico.json) | Duas séries históricas independentes: `comercial` (amostras do projeto) e `ptax` (fechamentos oficiais). |

Os arquivos são públicos e não exigem autenticação. São **endpoints JSON estáticos**, atualizados pelo workflow, e **não** uma API dinâmica ou serviço de cotação em tempo real.

## Origem e interpretação das cotações

| Série | Origem | Interpretação |
| --- | --- | --- |
| `comercial` | [AwesomeAPI, USD-BRL](https://economia.awesomeapi.com.br/json/last/USD-BRL) | Última cotação indicativa disponível quando o script executa. |
| `ptax` | [BCB, séries SGS 10813 e 1](https://dadosabertos.bcb.gov.br/dataset/10813-taxa-de-cambio---livre---dolar-americano-compra) | Taxa de referência do boletim oficial de **Fechamento**. |

**Atenção:** o valor comercial armazenado não representa necessariamente o fechamento do mercado. A PTAX não é uma cotação negociável e pode ter uma data anterior à observação comercial, sobretudo em feriados e fins de semana. A taxa efetiva de uma operação de câmbio depende das condições contratadas com a instituição financeira.

A página também disponibiliza links para consultas **diretas** à AwesomeAPI e ao BCB, independentes do ciclo de atualização deste projeto.

## Atualização automática

O workflow executa o script **diariamente às 21h UTC (18h em `America/Fortaleza`)**, com agendamento `0 21 * * *`, e também pode ser iniciado manualmente em **Actions → Atualizar cotações cambiais → Run workflow**. A execução agendada pode sofrer atrasos na infraestrutura do GitHub.

Em cada execução, o script:

1. Consulta separadamente a última cotação comercial `USD-BRL` na AwesomeAPI, usando a chave configurada no GitHub Actions.
2. Consulta as séries oficiais **SGS 10813 (compra) e SGS 1 (venda)**, para recuperar os fechamentos PTAX de até **120 dias corridos** anteriores, incluindo a data atual. Se a consulta por período falhar por instabilidade HTTP, tenta recuperar os últimos 20 registros de cada série.
3. Cruza as séries pela **mesma data**, excluindo observações sem par de compra e venda. As séries SGS são de fechamento diário, portanto não incluem boletins intermediários. Se ambas as consultas oficiais permanecerem indisponíveis, preserva a última PTAX oficial previamente confirmada; sem histórico oficial validado, a execução falha em vez de publicar uma taxa não confirmada.
4. Carrega o histórico existente, preserva as amostras comerciais anteriores e incorpora os fechamentos oficiais, com **um registro por data** em cada série.
5. Calcula a variação nominal e percentual da **compra PTAX** em relação ao fechamento anterior presente no histórico.
6. Atualiza `docs/historico.json` e `docs/cotacao.json`. O workflow registra as alterações na branch `main` e publica a pasta `docs/` no GitHub Pages.

A série comercial é **incremental**: registra as amostras obtidas quando o serviço roda, sem reconstruir retroativamente as cotações de mercado não capturadas. Já a série PTAX pode ser preenchida retroativamente com os fechamentos disponibilizados pelo BCB.

Em dias sem nova PTAX (por exemplo, fins de semana e feriados), o arquivo mantém o **último fechamento oficial existente** e sua **data de referência original**. Também pode não haver uma nova observação comercial. Não se deve interpretar `coletado_em` como data da PTAX ou como garantia de cotação recente.

Acompanhe as execuções em [GitHub Actions](https://github.com/mateusrodrigo/cotacoes-cambiais/actions).

## Formato dos dados

### `cotacao.json`

Contém um objeto com metadados da coleta e os dois registros mais recentes. Exemplo **ilustrativo** (valores e datas fictícios):

```json
{
  "par": "USD/BRL",
  "coletado_em": "2026-10-23T18:00:00-03:00",
  "fontes": {
    "comercial": "AwesomeAPI",
    "ptax": "Banco Central do Brasil"
  },
  "ptax_consulta_atualizada": true,
  "comercial": {
    "data": "2026-10-23",
    "data_hora": "2026-10-23T17:59:00-03:00",
    "timestamp": 1792789140,
    "compra": 5.038,
    "venda": 5.0402,
    "fonte": "AwesomeAPI",
    "tipo": "mercado_indicativo",
    "maxima": 5.055,
    "minima": 5.0266,
    "variacao": -0.0088,
    "variacao_percentual": -0.174178
  },
  "ptax": {
    "data": "2026-10-22",
    "compra": 5.0377,
    "venda": 5.0383,
    "fonte": "Banco Central do Brasil",
    "tipo_boletim": "Fechamento",
    "confirmada": true,
    "series_sgs": { "compra": 10813, "venda": 1 },
    "variacao": 0.0107,
    "variacao_percentual": 0.212852
  }
}
```

**O SGS não informa o horário da PTAX**, por isso os registros oficiais novos não incluem `data_hora` nem `timestamp`. O campo `ptax_consulta_atualizada` indica se foi possível consultar as séries oficiais nesta execução; `false` significa reutilização de fechamento confirmado anteriormente. Os campos de máxima, mínima e variação comercial aparecem quando disponibilizados pela AwesomeAPI. A PTAX não recebe máxima e mínima de mercado. A variação PTAX é calculada pelo próprio projeto e pode estar ausente no primeiro registro histórico.

### `historico.json`

Contém um **objeto**, não mais uma lista única:

```json
{
  "par": "USD/BRL",
  "comercial": [
    { "data": "2026-10-23", "compra": 5.038, "venda": 5.0402 }
  ],
  "ptax": [
    { "data": "2026-10-22", "compra": 5.0377, "venda": 5.0383 }
  ]
}
```

*Exemplo apenas estrutural: nos arquivos reais, cada registro inclui também os demais campos aplicáveis.* As listas são ordenadas da data mais antiga para a mais recente e consolidadas por data. As duas séries têm calendários e extensões potencialmente diferentes.

### Dicionário de campos

| Campo | Tipo | Significado |
| --- | --- | --- |
| `par` | string | Par cambial publicado: `USD/BRL`. |
| `coletado_em` | string | Horário de execução da coleta, em ISO 8601 com fuso de Fortaleza. |
| `fontes` | objeto | Identificação da origem de cada modalidade. |
| `data` | string | Data de referência da cotação, formato `AAAA-MM-DD`. |
| `data_hora` | string, opcional | Horário disponível para a amostra comercial. O SGS PTAX não informa horário. |
| `timestamp` | inteiro, opcional | Instante Unix da amostra comercial; não é criado artificialmente para os fechamentos SGS. |
| `compra`, `venda` | número | Taxas em **BRL por 1 USD**. |
| `fonte` | string | Provedor do registro. |
| `tipo` | string | Na série comercial, identifica a cotação como `mercado_indicativo`. |
| `tipo_boletim` | string | Identifica a série PTAX como `Fechamento`. |
| `series_sgs` | objeto | Códigos oficiais utilizados: compra `10813` e venda `1`. |
| `ptax_consulta_atualizada` | booleano | Em `cotacao.json`: indica consulta SGS concluída nesta execução. |
| `confirmada` | booleano | `true` nos fechamentos PTAX aceitos pelo script. |
| `maxima`, `minima` | número, opcional | Valores informados pela AwesomeAPI para a série comercial. |
| `variacao` | número, opcional | Variação nominal da compra. |
| `variacao_percentual` | número, opcional | Variação percentual da compra: `0.5` significa **0,5%**, não 50%. |

## Exemplo de consumo

```javascript
const base = "https://mateusrodrigo.github.io/cotacoes-cambiais";

const resposta = await fetch(`${base}/cotacao.json`);
if (!resposta.ok) {
  throw new Error(`Falha ao consultar cotações: HTTP ${resposta.status}`);
}

const dados = await resposta.json();
console.log("Comercial:", dados.comercial.compra, dados.comercial.data_hora);
console.log("PTAX:", dados.ptax.compra, dados.ptax.data, dados.ptax.confirmada);
```

Para escolher uma cotação histórica em um aplicativo, consulte `historico.json` e filtre `comercial` ou `ptax` pela data desejada. A escolha de **compra ou venda** e da **data de referência** deve respeitar a finalidade da operação ou do documento. Uma taxa manual informada pelo usuário é responsabilidade do aplicativo consumidor e não é publicada neste repositório.

## Estrutura do repositório

```text
.github/workflows/atualizar-cotacoes.yml  # Agendamento, commit e GitHub Pages
scripts/atualizar.py                     # Coleta, validação e histórico

docs/
  index.html                             # Página pública e links das fontes
  cotacao.json                           # Última comercial + última PTAX
  historico.json                         # Séries comercial e PTAX

README.md                                # Documentação
LICENSE                                  # Licença do código
```

## Configuração e publicação

- **Python:** 3.12, utilizando somente a biblioteca padrão.
- **Secret:** `AWESOME_API_KEY`, configurado em **Settings → Secrets and variables → Actions**. A chave é utilizada somente na consulta à AwesomeAPI e não deve constar no HTML ou nos JSONs.
- **Banco Central:** consulta pública via API SGS, sem necessidade de chave.
- **Publicação:** GitHub Pages com origem **GitHub Actions** e permissões adequadas para gravação na branch `main`.
- **Execução manual:** disponível no workflow `Atualizar cotações cambiais`.

Ao atualizar uma instalação antiga, **não exclua `docs/historico.json`**: o script migra o formato anterior, preservando as observações comerciais. Registros antigos de PTAX que não estejam identificados como fechamentos confirmados do BCB não são tratados como PTAX oficial. Depois da primeira execução bem-sucedida, os arquivos passarão a utilizar a nova estrutura.

## Disponibilidade e limitações

- A disponibilidade depende das APIs de origem e do GitHub Actions/Pages.
- O agendamento diário não assegura execução pontual nem observações em todos os dias.
- Falhas de coleta ou de validação podem interromper uma execução; aplicativos devem conferir `data`, `data_hora` e `coletado_em` antes de utilizar valores.
- A cotação comercial é uma amostra indicativa; não constitui taxa efetiva de contratação cambial.
- A PTAX é uma taxa oficial diária de referência, não uma cotação comercial continuamente atualizada. O SGS publica a data, sem horário intradiário; as duas séries precisam ser pareadas por data.
- Os aplicativos podem usar os endpoints JSON públicos ou consultar as APIs originais diretamente. As consultas diretas têm sua própria disponibilidade, condições e possíveis limites.

## Licença

O código deste repositório é distribuído sob a [licença MIT](LICENSE). O uso e a redistribuição dos dados devem respeitar as condições de cada provedor, inclusive as [condições da AwesomeAPI](https://docs.awesomeapi.com.br/api-de-moedas) e a [licença dos dados abertos do BCB](https://dadosabertos.bcb.gov.br/dataset/dolar-americano-usd-todos-os-boletins-diarios).

## Referências

- [Página pública do projeto](https://mateusrodrigo.github.io/cotacoes-cambiais/)
- [AwesomeAPI: API de Cotações](https://docs.awesomeapi.com.br/api-de-moedas)
- [AwesomeAPI: autenticação com API Key](https://docs.awesomeapi.com.br/instrucoes-api-key)
- [Banco Central: série SGS 10813, compra](https://dadosabertos.bcb.gov.br/dataset/10813-taxa-de-cambio---livre---dolar-americano-compra)
- [Banco Central: série SGS 1, venda](https://dadosabertos.bcb.gov.br/dataset/1-taxa-de-cambio---livre---dolar-americano-venda---diario)
- [Banco Central: documentação da API PTAX (Olinda)](https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/documentacao)
- [Banco Central: dólar comercial, cotações diárias e metodologia](https://dadosabertos.bcb.gov.br/dataset/dolar-americano-usd-todos-os-boletins-diarios)
- [GitHub Actions](https://docs.github.com/en/actions)
- [GitHub Pages: publicação com workflows personalizados](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
