# Política: ingestão — proveniência ancorada e julgamento reservado

A ingestão é o único lugar deste repositório onde **uma máquina escreve metadado**. A premissa da
casa é que o projeto declara e o padrão fiscaliza; um pipeline que escreve declarações fura essa
premissa a menos que duas coisas sejam verdade ao mesmo tempo.

## 1. Proveniência ancorada no SHA

Todo item ingerido carrega `derived_from: {repo, sha, path, section}`, e o fiscal cobra três
igualdades: `repo` é o alvo declarado, `sha` é **exatamente** o de `target.lock`, e `path` existe
no alvo materializado.

A do meio é a que carrega o peso. Sem ela, "este metadado descreve o alvo" degrada em silêncio
para "descrevia o alvo em algum momento" — que é o mesmo modo de falha que `target.lock` resolve
uma camada abaixo, e que aqui seria pior, porque o metadado *parece* atual. Um item cujo
`derived_from.sha` ficou para trás não é um detalhe de procedência: é uma afirmação sobre um
sistema que já mudou, feita com toda a confiança.

## 2. Julgamento reservado

A ingestão **não decide** `risk_level`, `likelihood`, `impact`, base legal, finalidade nem
criticidade. Escreve `pending_judgment`, e `check_pending_judgment` recusa esse valor em qualquer
documento com `source_of_truth: true`.

Isso parece o `to-be-assessed` que o `CLAUDE.md` proíbe, e é o oposto exato. Aquele é um campo
**aberto** que nenhum fiscal consegue reprovar — a pendência dura para sempre sem nunca aparecer
como falha. Este é **reprovável por construção**: ele só sobrevive enquanto o documento se declara
derivado, e o documento não pode virar fonte de verdade carregando um julgamento que ninguém fez.
Promover é substituir o sentinela, não redeclarar o cabeçalho.

O mesmo vale para `source_of_truth`. A ingestão escreve `false` com `generated_from` preenchido —
o `oneOf` que já existia em todos os schemas foi desenhado para isso. Virar `true` é ato humano.

## 3. O alvo é lido, nunca escrito

Nenhuma fase cria branch, commit, issue ou PR no alvo. `check_ingest_pipeline` reprova qualquer
`outputs` apontando para `workspace/` — escrever no material materializado seria escrita no
repositório de terceiro disfarçada de metadado local, e faria o vigia hospedar-se no vigiado.

## O que o pipeline é

`harness/pipeline/ingest.yaml` tem a mesma mecânica de `harness/stages.yaml`: índice verificável,
não segunda descrição. Cada fase declara `inputs`, `outputs`, `agent` (com contrato real em
`harness/agents/`) e um `fiscal` **resolvível** pela mesma função que resolve os fiscais das
etapas — duas implementações da pergunta "esse fiscal existe?" divergiriam com o tempo.

Fases que escrevem julgamento ou promovem metadado têm `gate: human_approval`. Uma fase que decide
sozinha o que só um humano pode decidir é a trava que o vigiado desliga.

## Limite honesto

Agrupar arquivos em componentes é julgamento de domínio, não dedução, e o `cartographer` vai errar
fronteira — principalmente em monorepo e em código que cresceu por acidente. É aceitável porque a
proposta vai por change-proposal e porque o erro fica **visível no diff, com a proveniência ao
lado**. O que não seria aceitável é o mesmo agente atribuir `risk_level` junto: aí o erro entraria
já vestido de julgamento humano, e ninguém reconferiria.

## Coleção vazia é estado de transição, nunca um lugar de descanso

Um derivado recém-adotado tem zero capacidades, zero componentes, zero interfaces e zero
requisitos — por construção, e por decisão declarada: o negócio de exemplo do molde descreve um
negócio que não existe ali. Enquanto os schemas exigiam um item, esse estado era inexprimível, e
sobravam duas saídas piores que o problema: inventar metadado de placeholder — a doença que este
repositório inteiro existe para combater — ou versionar arquivo que não valida contra o próprio
schema.

O piso saiu do schema e passou para o fiscal. Não é afrouxamento, é mudança de camada, e a razão é
estrutural: **um schema valida um documento**. Ele não enxerga `project.yaml` e não consegue
responder "este repositório já foi ingerido?". Um piso que não sabe distinguir "ainda não" de
"nunca" responde a pergunta errada com cara de erro estrutural.

Quem sabe distinguir é o fiscal, e o sinal é **declarado, não inferido**: `lifecycle: incubating`
num derivado suspende o piso; qualquer outro valor o cobra; e no molde ele vale sempre, porque o
exemplo é o substrato das asserções do ADR-005. Inferir a conclusão a partir do próprio arquivo
julgado — "a fase acabou porque a coleção está cheia" — seria circular e não reprovaria coleção
vazia alguma.

O desenho tem a propriedade que se quer de uma permissão temporária: **ela expira por um ato**. O
evento que a autoriza (adotar) é o que cria o estado, e promover o `lifecycle` é o que a revoga —
decisão de pessoa, num campo de enum fechado, e não efeito colateral de nada.

Duas coisas ficam de fora, e é deliberado. `business/rules/` não entra: as regras vivem em arquivo
por capacidade, então a ausência é o arquivo ausente, não uma lista vazia — e `check_business_rules`
percorre o diretório sem cobrar que ele tenha conteúdo. E o piso não protege sozinho: componente
exige `capability` no schema, e a invariante do código órfão exige componente, de modo que um
derivado com código real não consegue deixar essas duas coleções vazias nem que queira.

---

Fiscalizado por: `ci/validate_metadata.py::check_derived_from` (as três igualdades da
proveniência); `ci/validate_metadata.py::check_pending_judgment` (sentinela fora de documento
promovido); `ci/validate_metadata.py::check_collection_floor` (coleção vazia só em derivado com
`lifecycle: incubating`; a fase que preenche vem de `harness/pipeline/ingest.yaml`);
`ci/audit_governance.py::check_ingest_pipeline` (fase com agente e fiscal resolvíveis,
ordem sem duplicata, nenhuma escrita no alvo);
`harness/schemas/ingest-pipeline.schema.json`; `.github/workflows/governance.yml`.
Declarado em: `harness/pipeline/ingest.yaml`, `architecture/adr/index.yaml`,
`harness/agents/cartographer/`.
Falha como: proveniência divergente do lock, julgamento pendente em documento promovido, fase
sem fiscal ou coleção vazia fora da ingestão ⇒ exit 1; pipeline ilegível ⇒ exit 2.
