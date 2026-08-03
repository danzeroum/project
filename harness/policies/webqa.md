# Política: declarar o padrão, nunca copiar

O projeto consumidor declara a WebQA Suite como dependência versionada com pin exato (`==`). Ele
**não** contém uma cópia editável de `webqa/`, `checks/` ou `data/caminhos-sensiveis.yaml`.

## Por quê

`data/caminhos-sensiveis.yaml` é o que a sondagem procura em cada alvo. Ela tem teto imposto no
carregador, campos obrigatórios validados, e está sob CODEOWNERS — **na suíte**. Se cada projeto
tiver uma cópia editável, alguém remove uma linha que dava trabalho, a suíte para de procurar
aquilo naquele projeto, e o laudo continua dizendo "nenhum achado". Não há erro, não há aviso — o
resultado é indistinguível de um projeto seguro.

Uma trava que o vigiado pode desligar em silêncio não é uma trava.

## Se um projeto precisar de uma verificação própria

Ela vira proposta ao padrão, com dimensão declarada no `pytest.ini` **da suíte**, e passa a valer
para todos. Não vira arquivo solto no repositório do cliente. Se cada projeto tiver checks
próprios, o número que o cockpit produz deixa de ser comparável — e comparabilidade é a única razão
de existir um padrão.

---

Fiscalizado por: `.github/workflows/qa.yml` (passo que recusa `webqa/`, `checks/`,
`data/caminhos-sensiveis.yaml` versionados neste repo); pin exato validado contra
`WEBQA_CONSUMER_CONTRACT.md` §7.
Fiscalizado por (na suíte): `webqa/gates.py`, `data/` sob CODEOWNERS com teto `MAX_CAMINHOS`.
Falha como: erro de CI (achado, não silêncio).
