# Cotações Cambiais USD/BRL

Repositório de cotações do dólar americano em reais, com atualização diária automatizada e distribuição de dados em JSON. Disponibiliza a última cotação registrada e um histórico diário para consulta e integração com aplicações.

Os dados são obtidos da AwesomeAPI, processados em Python e publicados no GitHub Pages por meio do GitHub Actions.

## Dados disponíveis

| Arquivo | Conteúdo |
| --- | --- |
| [cotacao.json](https://mateusrodrigo.github.io/cotacoes-cambiais/cotacao.json) | Registro mais recente disponível no histórico. |
| [historico.json](https://mateusrodrigo.github.io/cotacoes-cambiais/historico.json) | Lista de registros diários, ordenada da data mais antiga para a mais recente. |

O acesso aos arquivos publicados não exige autenticação. Os valores de compra, venda, máxima e mínima são expressos em reais por dólar americano.

## Atualização automática

O workflow está agendado para executar uma vez por dia, às **21h UTC (18h em America/Fortaleza)**, e também permite execução manual.

Em cada execução, o processo:

1. Consulta as observações disponibilizadas pelo endpoint de histórico de 30 dias da AwesomeAPI.
2. Agrupa os registros pela data no fuso `America/Fortaleza`, preservando a observação com o timestamp mais recente de cada data.
3. Combina os dados recebidos com o histórico já armazenado, conservando os registros anteriores à janela consultada.
4. Atualiza os arquivos em `docs/`, registra as alterações no repositório e publica os JSONs no GitHub Pages.

A execução diária não implica uma nova cotação a cada dia. Em fins de semana, feriados ou períodos sem novas observações, a data e os valores podem permanecer iguais. Os horários de execução estão sujeitos a atrasos do GitHub Actions.

O acompanhamento das execuções está disponível na [aba Actions](https://github.com/mateusrodrigo/cotacoes-cambiais/actions).

## Formato dos registros

`cotacao.json` contém um objeto. `historico.json` contém uma lista de objetos com a mesma estrutura.

Exemplo de registro:

```json
{
  "data": "2026-10-15",
  "timestamp": 1792081950,
  "bid": 5.0482,
  "ask": 5.0487,
  "high": 5.0645,
  "low": 5.0375,
  "varBid": 0.0003,
  "pctChange": 0.005939
}
```

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `data` | string | Data da observação em `America/Fortaleza`, no formato `AAAA-MM-DD`. |
| `timestamp` | inteiro | Instante da observação em segundos Unix. |
| `bid` | número | Cotação de compra informada pela fonte. |
| `ask` | número | Cotação de venda informada pela fonte. |
| `high` | número | Máxima informada pela fonte. |
| `low` | número | Mínima informada pela fonte. |
| `varBid` | número | Variação nominal informada pela fonte. |
| `pctChange` | número | Variação percentual informada pela fonte; `0.005939` corresponde a `0,005939%`. |

O campo `data` representa a data da cotação, e não a data de execução ou publicação do workflow.

## Exemplo de consumo

```javascript
const resposta = await fetch(
  "https://mateusrodrigo.github.io/cotacoes-cambiais/cotacao.json"
);

if (!resposta.ok) {
  throw new Error(`Falha ao consultar cotação: HTTP ${resposta.status}`);
}

const cotacao = await resposta.json();
console.log(cotacao.data, cotacao.bid, cotacao.ask);
```

## Estrutura do projeto

```text
.github/workflows/atualizar-cotacoes.yml  # Automação e publicação
scripts/atualizar.py                     # Consulta e processamento dos dados
docs/                                   # Arquivos públicos e JSONs gerados
LICENSE                                 # Licença do código
```

## Configuração da automação

A automação utiliza Python 3.12 e a biblioteca padrão, sem dependências Python adicionais. A chave de consulta é fornecida pelo secret `AWESOME_API_KEY` do GitHub Actions e não é incluída nos JSONs.

A publicação requer o GitHub Pages configurado com origem **GitHub Actions**, permissão de escrita no conteúdo do repositório e regras de branch que permitam os commits da automação. O workflow utiliza a branch `main`.

## Fonte e disponibilidade

As cotações são indicativas e seguem os dados fornecidos pela AwesomeAPI. Não representam necessariamente a PTAX oficial nem a taxa efetiva aplicada por uma instituição financeira.

A disponibilidade depende da API de origem e dos serviços do GitHub. As aplicações consumidoras devem considerar a data da observação e tratar falhas de consulta. O histórico acumula os registros obtidos nas execuções; interrupções superiores à janela consultada podem deixar lacunas.

## Licença

O código é distribuído sob a [licença MIT](LICENSE). O uso e a redistribuição dos dados seguem as condições da fonte original.

## Referências

- [API de cotações da AwesomeAPI](https://docs.awesomeapi.com.br/api-de-moedas)
- [Autenticação da AwesomeAPI](https://docs.awesomeapi.com.br/instrucoes-api-key)
- [GitHub Actions](https://docs.github.com/en/actions)
- [Publicação com GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
