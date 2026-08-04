# Política: adoção — molde, alvo e derivado

Este repositório tem dois papéis possíveis, e confundi-los é a falha que esta política previne.

| Papel | `project.kind` | O que governa |
|---|---|---|
| **molde** | `mold` | nada. É a casca genérica, reaproveitável por qualquer alvo. |
| **derivado** | `derived` | exatamente **um** alvo, declarado em `project.yaml:target` |

## A regra

**O derivado declara o alvo, nunca o copia.** O código do alvo materializa em `workspace/target/`
— efêmero, fora do versionamento — no commit exato de `target.lock`. O derivado versiona só o que
é dele: metadados, laudos e o lock.

É a mesma decisão do ADR-001 aplicada a outro objeto. Lá, copiar a régua para dentro do projeto
permitiria remover uma linha da lista curada e o laudo passaria a dizer "nenhum achado" sem erro
nem aviso. Aqui, copiar o código do alvo cria uma fonte paralela que deriva do original em
silêncio — e o metadado passa a descrever, com toda a confiança, um sistema que não existe mais.

## Fonte única do SHA

`project.yaml` declara **qual** alvo (`repo`, `ref`) e **onde** o SHA mora (`lock_source`).
O número mora só em `target.lock`. Idêntico a `quality_standard.version_source` →
`requirements-qa.txt`, e pela mesma razão: duas cópias de uma versão derivam, e a comparação entre
"o que o metadado descreve" e "o que o alvo é hoje" passa a mentir. `ADR-008-A4` reprova qualquer
SHA de commit que apareça em `project.yaml`.

## Nenhum alvo é especial

A genericidade é o produto deste repositório, então ela é fiscalizada, não prometida:
**`ci/` e `harness/` não mencionam nenhum alvo** — nem nome, nem stack, nem caminho, nem URL.
`ADR-008-A5` reprova se mencionarem.

O ponto não é estética. Um molde que ganhou um `if` para o alvo difícil de ontem funciona para
aquele alvo e falha silenciosamente para os outros — e falha *parecendo* que funcionou, porque o
caminho especial passa e o caminho geral nunca é exercitado. Tudo que é do alvo mora em três
lugares, todos fora dos fiscais: `project.yaml:target`, `target.lock` e `workspace/`.

## Descobrir, nunca presumir

`ref`, `code_roots` e `languages` são **descobertos** no reconhecimento do alvo e declarados.
Nada é presumido por convenção — nem que a branch padrão se chama `main`, nem que o código mora em
`src/`, nem que existe uma linguagem só.

E raiz declarada que não existe no alvo é achado (`check_target_roots`), não detalhe: um
`code_roots` chutado torna a invariante do código órfão verdadeira **por vacuidade** — o fiscal
percorre um conjunto vazio, não acha nada e reporta verde. É a pior falha possível aqui, porque é
indistinguível de cobertura real.

## O estado intermediário que não existe

O par `kind`/`target_sha` é travado nos dois sentidos pelo schema: molde não ancora SHA, derivado
sem SHA não valida. Não há "derivado quase pronto" — estado que, uma vez tolerado, dura para
sempre, porque nenhum fiscal o reprova e ninguém volta para terminá-lo.

## Limite honesto

O reconhecimento do alvo (passo 2 do `/adotar`) é julgamento de agente, não dedução mecânica:
decidir que `packages/` é raiz de código e `scripts/` não é uma leitura do domínio. O fiscal
verifica o que foi **declarado** contra o alvo materializado — ele reprova raiz inexistente, mas
não descobre raiz esquecida. Quem fecha essa porta é a invariante do código órfão (Fase C):
arquivo sob `code_roots` sem componente reprova, e arquivo fora de `code_roots` fica visível como
território não declarado.

---

Fiscalizado por: `ci/validate_metadata.py::check_target_lock` (o papel declarado é o mesmo nos dois
arquivos, e a âncora do SHA aponta para `target.lock`);
`ci/validate_metadata.py::check_target_roots` (raiz declarada existe no alvo materializado);
`harness/schemas/target-lock.schema.json` (molde não ancora SHA; derivado exige commit válido);
`harness/schemas/project.schema.json` (`derived` exige `target`; `mold` o proíbe);
`ci/audit_governance.py` (executa as asserções do ADR-008).
Declarado em: `architecture/adr/index.yaml`, `project.yaml`, `target.lock`.
Falha como: papel ou âncora divergentes ⇒ exit 1; alvo cravado em `ci/` ou `harness/` ⇒ achado
`FIND-ADR-008-A5` e exit 1.
