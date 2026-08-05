# Cadeia de decisão — um parecer não fecha enquanto seus achados não forem consumidos

Dois pareceres vivem em `governance/`: o de conformidade e o de privacidade. Ambos existem porque
fiscal determinístico não julga se uma descrição ainda condiz com a realidade — ele confere que
alguém julgou.

O que esta política acrescenta é o outro lado: **o que aconteceu com o que foi julgado.**

## A regra

Achado com disposição de encaminhamento (`change_proposal`, `risk_entry`) declara
`consumed_by = {kind, ref}`, e o `ref` **resolve** contra o artefato real — a proposta existe como
arquivo, o `RISK-*` existe no registro, o `ADR-*` existe no índice.

Issue de privacidade `P0`/`P1` que segue aberto ou mitigado declara o mesmo. O schema já cobrava um
`RISK-*`; faltava o simétrico: um risco registrado sem trabalho declarado é um risco gerido apenas
no papel.

`accepted` continua sendo saída legítima, e continua exigindo `rationale`. O que se recusa é o
achado que sai do parecer sem **nenhuma** decisão.

## Por que resolver, e não apenas exigir o campo

Antes existia `ref`, opcional e de texto livre. "Este achado virou uma change-proposal" era uma
afirmação que ninguém conferia. **Um achado encaminhado para o vazio é indistinguível de um achado
tratado** — e a diferença entre os dois é a única coisa que o parecer produz.

Destino que não resolve é achado, pela mesma lógica do `assertion_unresolvable` do ADR-006: uma
trava que não encontra o que vigia está quebrada, não satisfeita.

## Sobre a forma que foi rejeitada

A ideia nasceu como **tipos lineares em runtime** e a forma foi rejeitada (R-02): não há runtime
aqui, e inventar um para carregar a metáfora seria a inversão que o R-03 recusou. A intenção
sobreviveu como declaração resolvível. O registro fica aqui para que a forma não seja reproposta
sem enfrentar o motivo da rejeição.

Fiscalizado por: `ci/audit_governance.py::check_decision_chain`, `harness/schemas/conformance-review.schema.json`, `harness/schemas/privacy-review.schema.json`
Declarado em: `harness/change-proposals/CP-023-consumo-obrigatorio-de-pareceres.yaml`
Falha como: achado encaminhado sem `consumed_by`, ou com destino que não resolve ⇒ achado bloqueante.
