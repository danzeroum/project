<!-- GENERATED: não editar; rodar ci/generate_schema_docs.py -->
# Referência dos schemas

Derivado de `harness/schemas/*.json`. As descrições vêm dos próprios schemas — este
documento não acrescenta significado, ele torna legível o que já está declarado.

Um campo sem descrição aqui é um campo sem descrição **no schema**: o lugar de corrigir
é lá.

## `adr-index.schema.json`

**architecture/adr/index.yaml — índice fiscalizável de ADRs**

> Os ADRs são prosa (markdown); o índice é a parte verificável: cada entrada aponta para um arquivo real, resolve suas referências (CAP/CMP/RISK/ADR) e declara ASSERÇÕES executáveis. A seção '## Fiscal' de cada ADR nomeia o fiscal em prosa; assertions[] é a mesma coisa numa forma que a máquina executa. Um ADR aceito sem asserção é, ele próprio, o que o ADR-002 proíbe.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `adrs` | array<object> | sim |  |
| `adrs[].id` | string | sim |  |
| `adrs[].title` | string | sim |  |
| `adrs[].status` | enum(proposed · accepted · superseded · deprecated) | sim |  |
| `adrs[].file` | string | sim |  |
| `adrs[].supersedes` | array<string> | — |  |
| `adrs[].related_capabilities` | array<string> | — |  |
| `adrs[].related_components` | array<string> | — |  |
| `adrs[].related_risks` | array<string> | — |  |
| `adrs[].assertions` | array<—> | — |  |

## `audit-report.schema.json`

**Laudo dos fiscais locais de conformidade e privacidade**

> Irmão de report.schema.json, NÃO derivado dele. Aquele envelope carrega a procedência do padrão externo WebQA (standard.version, consumer_project, execution.mode); estes fiscais são outro produtor — scripts deste repositório, sem régua externa e sem modo de suíte. Forçá-los naquele envelope produziria campos mentirosos.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | const(1.0) | sim |  |
| `provenance` | object | sim | Quem produziu o laudo, sobre qual estado do repositório. |
| `provenance.auditor` | enum(ci/audit_governance.py · ci/audit_lgpd.py · ci/alignment_report.py · ci/audit_conformance.py · ci/audit_ledger.py · ci/check_dependency_conflict.py) | sim |  |
| `provenance.auditor_version` | string | sim |  |
| `provenance.repository` | string | sim |  |
| `provenance.commit` | string | sim |  |
| `provenance.generated_at` | string | sim |  |
| `provenance.stages_covered` | array<string> | sim |  |
| `provenance.scope_fingerprint` | string | — |  |
| `result` | enum(ok · findings · error) | sim | ok = o real corresponde ao declarado; findings = há divergência; error = o fiscal não conseguiu fiscalizar. |
| `summary` | object | sim |  |
| `summary.total` | integer | sim |  |
| `summary.by_severity` | object | sim |  |
| `findings` | array<object> | sim | Divergências entre o declarado e o real. severity é TRIAGEM, não gate: com fail-closed qualquer achado derruba o CI. |
| `findings[].id` | string | sim |  |
| `findings[].origin` | enum(adr_assertion · adr_meta · assertion_self_match · stage_coverage · stage_partition · policy_pointer · risk_control · protected_path · lgpd_inventory · lgpd_scan · lgpd_retention · lgpd_declaration · lgpd_judgment · manual_assertion · ingest_pipeline · alignment_risk · alignment_orphan · conformance_review · cp_lifecycle · decision_chain · change_buffer · external_audit · ledger · agent_pairing · dependency_conflict) | sim |  |
| `findings[].severity` | enum(info · low · medium · high · critical) | sim |  |
| `findings[].summary` | string | sim |  |
| `findings[].adr` | string | — |  |
| `findings[].assertion` | string | — |  |
| `findings[].stage` | string | — |  |
| `findings[].risk` | string | — |  |
| `findings[].location` | string | — |  |
| `findings[].evidence` | string | — |  |
| `findings[].remediation` | string | — |  |
| `findings[].lgpd_article` | string | — |  |
| `findings[].pbd_principle` | enum(Proativo e Preventivo · Privacy by Default · Privacidade no Design · Soma Positiva · Transparência · Segurança Ponta-a-Ponta · Centrado no Usuário) | — |  |

## `backlog.schema.json`

**business/requirements/backlog.yaml — requisitos ligados a capacidades**

> Cada item de backlog pertence a uma capacidade (CAP-*). Dá ao agente o QUE precisa ser feito e por quê, sem inventar escopo.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `items` | array<object> | sim |  |
| `items[].id` | string | sim |  |
| `items[].title` | string | sim |  |
| `items[].type` | enum(user-story · task · bug · enabler) | sim |  |
| `items[].capability` | string | sim |  |
| `items[].status` | enum(proposed · planned · in_progress · done · dropped) | sim |  |
| `items[].priority` | enum(low · medium · high · critical) | sim |  |
| `items[].acceptance_criteria` | array<string> | — |  |
| `items[].depends_on` | array<string> | — |  |
| `items[].risk` | string | — |  |
| `items[].metrics` | array<string> | — |  |
| `items[].governed_by` | array<string> | — |  |
| `items[].validated_by` | array<string> | — |  |
| `items[].derived_from` | object | — | Proveniência da ingestão: de ONDE no alvo este item foi derivado, e em QUE commit. Sem o sha, 'este metadado descreve o alvo' vira afirmação sobre um alvo que já mudou — o mesmo modo de falha que target.lock resolve, uma camada acima. ci/validate_metadata.py::check_derived_from cobra que repo casa target.repo, que sha casa target.lock exatamente e que path existe no alvo materializado. |
| `items[].derived_from.repo` | string | sim |  |
| `items[].derived_from.sha` | string | sim |  |
| `items[].derived_from.path` | string | sim | Relativo à raiz do alvo, sem o prefixo workspace/target/. |
| `items[].derived_from.section` | string | — | Âncora dentro do arquivo (título de seção, símbolo). Opcional: nem toda origem tem subdivisão. |

## `bootstrap-report.schema.json`

**harness/state/bootstrap.json — laudo do cold start**

> Evidência de execução, não fonte de verdade: vive em harness/state/ (gitignored) e é reescrito a cada bootstrap. Tem schema pela mesma razão que audit-report.schema.json tem — um laudo que ninguém valida é markdown que não morde, e ci/bootstrap.py valida o próprio laudo ANTES de gravá-lo. O campo resultado distingue as três saídas que o repositório inteiro usa: ok, divergencias (exit 1) e fiscal-nao-fiscalizou (exit 2); um bootstrap que não conseguiu levantar o ambiente nunca se declara ok.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `kind` | enum(mold · derived) | — |  |
| `resultado` | enum(ok · divergencias · fiscal-nao-fiscalizou · erro) | — |  |
| `erro` | string | — |  |
| `proximo_passo` | string | — |  |
| `etapas` | object | sim |  |
| `etapas.ambiente` | object | — |  |
| `etapas.ambiente.python` | string | — |  |
| `etapas.ambiente.git` | string | — |  |
| `etapas.dependencias` | object | — |  |
| `etapas.dependencias.instalado_agora` | boolean | — |  |
| `etapas.drift` | object | — | Distância entre target.lock e o remoto. Reportada, nunca corrigida aqui: avançar o lock é decisão declarada, e movê-lo sem revisar o metadado troca um drift visível por um metadado errado. |
| `etapas.drift.estado` | enum(em-dia · atrasado · indisponivel) | sim |  |
| `etapas.drift.sha` | string | — |  |
| `etapas.drift.lock` | string | — |  |
| `etapas.drift.remoto` | string | — |  |
| `etapas.drift.ref` | string | — |  |
| `etapas.drift.motivo` | string | — |  |
| `etapas.workspace` | object | — |  |
| `etapas.workspace.acao` | enum(materializado · avancado · ja-no-sha · nao-aplicavel) | sim |  |
| `etapas.workspace.sha` | string | — |  |
| `etapas.workspace.de` | string | — |  |

## `business-rules.schema.json`

**business/rules/*.yaml — regras de negócio de uma capacidade**

> Regras declaradas por capacidade. Reduzem o risco de um agente implementar algo tecnicamente correto mas funcionalmente inadequado.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `capability` | string | sim |  |
| `rules` | array<object> | sim |  |
| `rules[].id` | string | sim |  |
| `rules[].name` | string | sim |  |
| `rules[].status` | enum(proposed · planned · implemented · verified · deprecated) | sim |  |
| `rules[].statement` | string | sim |  |
| `rules[].rationale` | string | — |  |
| `rules[].verified_by` | array<string> | — |  |

## `capabilities.schema.json`

**capabilities.yaml — capacidades de negócio com rastreabilidade física**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `capabilities` | array<object> | sim |  |
| `capabilities[].id` | string | sim |  |
| `capabilities[].name` | string | sim |  |
| `capabilities[].status` | enum(proposed · planned · implemented · verified · deprecated) | sim | Maturidade. O fiscal semântico só exige código+teste existentes para implemented/verified. |
| `capabilities[].owners` | object | sim |  |
| `capabilities[].owners.business_owner` | string | sim |  |
| `capabilities[].owners.technical_owner` | string | sim |  |
| `capabilities[].risk_level` | enum(low · medium · high · critical · pending_judgment) | sim | Nível de risco da capacidade. pending_judgment é o valor que a INGESTÃO escreve por não poder decidir: reprovado por check_pending_judgment em qualquer documento com source_of_truth:true, logo só sobrevive enquanto o documento se declara derivado. Promover é substituí-lo. |
| `capabilities[].source_paths` | array<string> | sim |  |
| `capabilities[].test_paths` | array<string> | sim |  |
| `capabilities[].business_rules` | array<string> | — |  |
| `capabilities[].evidence` | object | — | Referências LÓGICAS a evidência. quality_reports pode apontar para dir gitignored — é referência, não garantia de arquivo versionado. |
| `capabilities[].evidence.tests` | array<string> | — |  |
| `capabilities[].evidence.architecture` | array<string> | — |  |
| `capabilities[].evidence.quality_reports` | array<string> | — |  |
| `capabilities[].derived_from` | object | — | Proveniência da ingestão: de ONDE no alvo este item foi derivado, e em QUE commit. Sem o sha, 'este metadado descreve o alvo' vira afirmação sobre um alvo que já mudou — o mesmo modo de falha que target.lock resolve, uma camada acima. ci/validate_metadata.py::check_derived_from cobra que repo casa target.repo, que sha casa target.lock exatamente e que path existe no alvo materializado. |
| `capabilities[].derived_from.repo` | string | sim |  |
| `capabilities[].derived_from.sha` | string | sim |  |
| `capabilities[].derived_from.path` | string | sim | Relativo à raiz do alvo, sem o prefixo workspace/target/. |
| `capabilities[].derived_from.section` | string | — | Âncora dentro do arquivo (título de seção, símbolo). Opcional: nem toda origem tem subdivisão. |

## `change-proposal.schema.json`

**change-proposal — a ponte entre metadado estático e execução agentic**

> Toda mudança proposta (por agente, humano ou CI) declara o que afeta, o risco, os gates exigidos e se precisa de aval humano. É o que a harness lê para rotear, bloquear ou escalar.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `proposal` | object | sim |  |
| `proposal.id` | string | sim |  |
| `proposal.title` | string | sim |  |
| `proposal.author_kind` | enum(agent · human · ci) | sim |  |
| `proposal.created_at` | string | sim |  |
| `proposal.capabilities_affected` | array<string> | sim |  |
| `proposal.components_affected` | array<string> | sim |  |
| `proposal.risk_assessment` | object | sim |  |
| `proposal.risk_assessment.level` | enum(low · medium · high · critical) | sim |  |
| `proposal.risk_assessment.risks` | array<string> | — |  |
| `proposal.risk_assessment.rationale` | string | sim |  |
| `proposal.required_gates` | array<enum(inventory · passive · load · active_discovery · unit-tests · metadata-validation)> | sim |  |
| `proposal.tests_required` | array<string> | sim |  |
| `proposal.human_approval_required` | boolean | sim |  |
| `proposal.change_mode` | const(pull_request) | sim |  |
| `proposal.status` | enum(draft · approved · executed · rejected · superseded · deferred) | — | Onde a proposta está no ciclo. 'deferred' é estado de primeira classe: uma CP que depende de condição externa (identidade emissora, ADR de exceção) não conta como implementada, e sem este valor ela ficaria eternamente 'approved' passando por pronta. |
| `proposal.paths_affected` | array<string> | — | Caminhos que a proposta toca. Diferente de capabilities/components: aqueles descrevem o NEGÓCIO afetado, este descreve a SUPERFÍCIE editada — e é o que permite ao fiscal de atrito perguntar se o mesmo lugar está sendo reproposto sem parar. |
| `proposal.executed_in` | object | — | Onde a proposta foi integrada. Para risco alto, merge_commit_sha é obrigatório: número de PR é ponteiro para uma conversa, merge commit é o conteúdo. |
| `proposal.executed_in.pr_number` | integer | sim |  |
| `proposal.executed_in.merge_commit_sha` | string | — |  |
| `proposal.approved_by` | object | — | Quem aprovou, e com QUAL review. O login sozinho é texto que o autor digita; o review_id é o que ci/verify_approval.py resolve contra a API — inclusive para recusar aprovação anterior ao último push. |
| `proposal.approved_by.login` | string | sim |  |
| `proposal.approved_by.review_id` | integer | sim |  |
| `proposal.approved_by.pr_number` | integer | sim |  |
| `proposal.approved_by.approved_at` | string | sim |  |

## `components.schema.json`

**components.yaml — componentes técnicos ligados a capacidades**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `components` | array<object> | sim |  |
| `components[].id` | string | sim |  |
| `components[].kind` | enum(domain-module · adapter · port · service · ui-surface) | sim |  |
| `components[].capability` | string | sim |  |
| `components[].status` | enum(proposed · planned · implemented · verified · deprecated) | sim |  |
| `components[].source_paths` | array<string> | sim |  |
| `components[].depends_on` | array<string> | — |  |
| `components[].exposes` | array<string> | — |  |
| `components[].tested_by` | array<string> | sim |  |
| `components[].implements` | array<string> | — |  |
| `components[].owner` | string | sim |  |
| `components[].derived_from` | object | — | Proveniência da ingestão: de ONDE no alvo este item foi derivado, e em QUE commit. Sem o sha, 'este metadado descreve o alvo' vira afirmação sobre um alvo que já mudou — o mesmo modo de falha que target.lock resolve, uma camada acima. ci/validate_metadata.py::check_derived_from cobra que repo casa target.repo, que sha casa target.lock exatamente e que path existe no alvo materializado. |
| `components[].derived_from.repo` | string | sim |  |
| `components[].derived_from.sha` | string | sim |  |
| `components[].derived_from.path` | string | sim | Relativo à raiz do alvo, sem o prefixo workspace/target/. |
| `components[].derived_from.section` | string | — | Âncora dentro do arquivo (título de seção, símbolo). Opcional: nem toda origem tem subdivisão. |
| `exemptions` | array<object> | sim | Arquivos sob code_roots OU test_roots que deliberadamente nao pertencem a componente algum — fixture, stub, conftest, snapshot, shim. Mesma mecanica de stages.yaml:ungoverned, incluindo a propriedade que a torna honesta: isencao que nao casa arquivo nenhum e ela propria um achado. Ate a CP-039 so check_orphan_code a consultava, e declarar um arquivo de apoio de TESTE produzia achado de isencao morta sem reduzir o contador de teste orfao — a trava recusava a declaracao que ela propria prescrevia. Lista vazia e declaracao valida. |
| `exemptions[].path` | string | sim |  |
| `exemptions[].justification` | string | sim |  |

## `conformance-review.schema.json`

**governance/conformance-review.yaml — registro tipado da VALIDAÇÃO semântica**

> Irmão de privacy-review.yaml, e pela mesma razão: separar o julgamento (prosa, feita por agente) do registro (tipado, fiscalizável) é o que permite conferir sem tentar conferir prosa. O fiscal determinístico não julga se a descrição de um componente ainda condiz com o código — ele confere que alguém julgou, e que o julgamento cobre ESTE estado, incluindo o SHA do alvo. Verificação e validação são coisas distintas: verificar é 'está conforme o declarado?' (fiscal); validar é 'ainda faz o que deveria?' (agente).

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `review` | object | sim |  |
| `review.produced_by` | enum(agent · human) | sim |  |
| `review.agent` | const(conformance) | sim |  |
| `review.scope_fingerprint` | string | sim | Cobre o metadado governável E o SHA de target.lock. Recalcular: python ci/audit_conformance.py --print-fingerprint |
| `review.findings` | array<object> | sim | O que o agente achou. Cada achado vira change-proposal ou entrada de risco — NUNCA correção direta: um agente que conserta o que ele mesmo julga é juiz e parte. |
| `review.findings[].id` | string | sim |  |
| `review.findings[].severity` | enum(low · medium · high · critical) | sim |  |
| `review.findings[].summary` | string | sim |  |
| `review.findings[].disposition` | enum(change_proposal · risk_entry · accepted) | sim | Para onde o achado foi encaminhado. 'accepted' exige rationale — aceitar em silêncio é como um achado morre. |
| `review.findings[].ref` | string | — |  |
| `review.findings[].rationale` | string | — |  |
| `review.findings[].consumed_by` | object | — | Para qual artefato REAL o achado foi. Traducao declarativa dos tipos lineares (R-02): a forma em runtime foi rejeitada, a intencao sobreviveu como destino resolvivel. ci/audit_governance.py::check_decision_chain resolve o ref. |
| `review.findings[].consumed_by.kind` | enum(change_proposal · risk · adr) | sim |  |
| `review.findings[].consumed_by.ref` | string | sim |  |
| `review.not_assessed` | array<string> | sim | O que a revisão NÃO olhou. Registrar isto é requisito: 'sem achados' numa categoria que ninguém examinou é a forma mais silenciosa de laudo falso. |

## `data-inventory.schema.json`

**governance/data-inventory.yaml — inventário de dados pessoais**

> Registro das operações de tratamento (Lei 13.709/2018, Art. 37): que dado pessoal existe, para qual finalidade, sob qual base legal, por quanto tempo e sob qual componente. Nasce vazio; a partir do primeiro campo o schema passa a exigir encarregado (Art. 41) e o fiscal passa a exigir RIPD completo (Art. 38).

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `controller` | object | sim |  |
| `controller.role` | enum(none · incidental · controller · operator · controller_and_operator) | sim |  |
| `controller.dpo_contact` | string | — |  |
| `purposes` | array<object> | sim |  |
| `purposes[].id` | string | sim |  |
| `purposes[].description` | string | sim |  |
| `purposes[].legal_basis` | — | sim |  |
| `fields` | array<—> | sim |  |
| `subject_rights` | object | sim | Art. 18. Não existe direito do titular sem endpoint: se confirmação, acesso, eliminação ou portabilidade não têm onde ser exercidos, o direito não existe no sistema. |
| `subject_rights.confirmation` | string | null | sim |  |
| `subject_rights.access` | string | null | sim |  |
| `subject_rights.deletion` | string | null | sim |  |
| `subject_rights.portability` | string | null | sim |  |
| `international_transfer` | array<object> | — |  |
| `international_transfer[].destination` | string | sim |  |
| `international_transfer[].mechanism` | enum(adequacao · clausulas_padrao · clausulas_especificas · selos_certificados · consentimento_especifico) | sim |  |
| `international_transfer[].fields` | array<string> | sim |  |
| `scan` | object | sim | Supressões da varredura de dado pessoal. A régua (os léxicos) vive em ci/audit_lgpd.py como constante, não em YAML editável: suprimir é DECLARAR aqui com motivo, nunca apagar um termo da lista. |
| `scan.exclusions` | array<object> | sim |  |
| `scan.exclusions[].path_glob` | string | sim |  |
| `scan.exclusions[].token` | string | sim |  |
| `scan.exclusions[].justification` | string | sim |  |

## `dependencies.schema.json`

**security/dependencies.yaml — inventário de dependências (SBOM leve)**

> A direção reversa da Fase E aplicada a supply chain. Os fiscais já sabiam que a régua está pinada; ninguém verificava que TODA dependência declarada em pyproject.toml e requirements-qa.txt está inventariada, com dono e razão. Dependência declarada e não inventariada é achado — acrescentar biblioteca passa a exigir passar por aqui, que é o efeito pretendido.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `dependencies` | array<object> | sim |  |
| `dependencies[].name` | string | sim | Nome normalizado do pacote, minúsculo. |
| `dependencies[].scope` | enum(runtime · dev · qa) | sim | runtime é o que chega ao usuário; dev e qa não. A distinção muda o que uma vulnerabilidade significa. |
| `dependencies[].declared_in` | string | sim | Arquivo onde a dependência é declarada. Cobrado por ci/validate_metadata.py::check_dependency_inventory — inventário que aponta para arquivo inexistente não vigia nada. |
| `dependencies[].pin_kind` | enum(exact · range · unpinned) | sim | Descreve o que É, não o que deveria ser. 'range' declarado é uma decisão auditável; 'range' escondido é uma dependência que muda sozinha entre dois runs. |
| `dependencies[].owner` | string | sim |  |
| `dependencies[].purpose` | string | sim | Por que ela existe. Dependência sem razão registrada é a que ninguém ousa remover. |

## `design-system.schema.json`

**design-system.yaml — identidade e metas do sistema de design**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `design_system` | object | sim |  |
| `design_system.name` | string | sim |  |
| `design_system.version` | string | sim |  |
| `design_system.accessibility_target` | enum(WCAG-2.1-AA · WCAG-2.2-AA · WCAG-2.2-AAA) | sim |  |

## `harness.schema.json`

**harness.yaml**

> Plano de controle da harness. Auto-validável: todo modo/runner/env que a harness declara é checado aqui.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | integer | sim |  |
| `repository` | object | sim |  |
| `repository.project_manifest` | string | sim |  |
| `repository.stages_manifest` | const(harness/stages.yaml) | sim | Manifesto das etapas do projeto: fonte única de quais etapas existem e quem as fiscaliza. ci/audit_governance.py exige que todo arquivo do repositório pertença a uma delas ou a uma isenção declarada. |
| `repository.protected_paths` | array<string> | sim | Caminhos que só mudam com revisão humana. Fiscal real: CODEOWNERS + branch protection + diff-check no CI. |
| `decision_policy` | object | sim |  |
| `decision_policy.default` | const(deny) | sim | Se a harness não reconhece projeto, capacidade, risco ou modo, ela NÃO infere que pode agir. |
| `decision_policy.missing_metadata` | const(stop_and_request_context) | sim |  |
| `decision_policy.protected_path_change` | const(require_human_review) | sim |  |
| `decision_policy.dependency_update` | const(require_human_review) | sim |  |
| `standard` | object | sim |  |
| `standard.package` | string | sim |  |
| `standard.requirements_file` | string | sim | O pin exato vive aqui; harness.yaml apenas referencia. |
| `execution_modes` | object | sim | Os quatro modos DEVEM estar todos presentes. |
| `execution_modes.inventory` | — | sim |  |
| `execution_modes.passive` | — | sim |  |
| `execution_modes.load` | — | sim |  |
| `execution_modes.active_discovery` | — | sim |  |
| `env_hygiene` | object | sim |  |
| `env_hygiene.env_allowlist` | array<string> | sim |  |
| `env_hygiene.env_denylist_prefix` | array<string> | sim |  |
| `env_hygiene.fail_on_denied_env` | boolean | sim |  |
| `env_hygiene.env_denylist_exact` | array<string> | sim | Nomes EXATOS proibidos. Distinta de env_denylist_prefix porque a ameaça é outra: prefixo cobre a familia WEBQA_* (auto-autorizacao); estes nomes redirecionam de onde o processo busca o que executa. minItems 1 para que esvaziar a lista seja tao visivel quanto remover a chave. |
| `env_hygiene.exceptions` | array<object> | — | Excecao DECLARADA a denylist. Cada uma nomeia contexto e justificativa: excecao declarada e contestavel numa revisao; entrada removida da lista e excecao que ninguem mais ve. |
| `env_hygiene.exceptions[].name` | string | sim |  |
| `env_hygiene.exceptions[].context` | string | sim |  |
| `env_hygiene.exceptions[].justification` | string | sim |  |
| `paths` | object | sim |  |
| `paths.runs` | string | sim |  |
| `paths.reports` | string | sim |  |
| `paths.state` | string | sim |  |
| `target_feedback` | object | — | Canal de retorno derivado -> alvo: a única capacidade que escreveria num repositório de terceiro. Ambos os campos nascem no lado fechado, coerentes com decision_policy.default: deny. O schema não força o valor — força a DECLARAÇÃO: quem ligar o canal escreve true num arquivo protegido, sob revisão, em vez de o comportamento aparecer por omissão. |
| `target_feedback.open_issues_on_target` | boolean | sim |  |
| `target_feedback.requires_human_approval` | boolean | sim |  |
| `external_audit` | object | sim | Camada externa da trava. DECLARADA mesmo desligada: sem este bloco, 'nao ha autoridade externa' seria um estado sem lugar onde aparecer, e uma lacuna que nao aparece nao e revisada. |
| `external_audit.enabled` | boolean | sim |  |
| `external_audit.accepted_risk` | string | sim | Enquanto enabled e false, o risco aceito COM DATA que cobre a janela. Sem este elo, desligar a camada externa nao custaria nada a ninguem. |
| `external_audit.attestation_path` | string | sim |  |
| `external_audit.justification` | string | sim |  |
| `external_audit.authorized_issuer` | object | — | QUEM pode atestar. Sem este bloco, `issuer` no atestado seria um campo exigido pelo schema e conferido por ninguém — 'alguém atestou' passando por 'quem devia atestou'. Quem tem direito de merge escreveria o JSON à mão e o molde aceitaria. |
| `external_audit.authorized_issuer.identity` | string | sim |  |
| `external_audit.authorized_issuer.kind` | enum(github_app · oidc_workload · external_service) | sim |  |

## `ingest-pipeline.schema.json`

**harness/pipeline/ingest.yaml — as fases da ingestão e seus fiscais**

> Mesma mecânica de stages.yaml: índice verificável, nunca segunda descrição. Cada fase declara inputs, outputs, o agente que a executa e um fiscal RESOLVÍVEL — fase sem fiscal é trabalho que ninguém confere, e num pipeline que escreve metadado isso é pior do que não ter o pipeline. O que este arquivo deliberadamente não tem: qualquer escrita no alvo. A ingestão lê o alvo e escreve no derivado.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `phases` | array<object> | sim |  |
| `phases[].id` | string | sim |  |
| `phases[].order` | integer | sim |  |
| `phases[].name` | string | sim |  |
| `phases[].agent` | string | sim | Subpasta de harness/agents/ com o contrato do agente. Cobrado por ci/audit_governance.py::check_ingest_pipeline — agente citado sem contrato é fase sem dono. |
| `phases[].inputs` | array<string> | sim | Caminhos ou globs lidos. workspace/target/** é o alvo materializado; tudo mais é deste repositório. |
| `phases[].outputs` | array<string> | sim | Caminhos escritos. Nenhum pode estar fora deste repositório: a ingestão lê o alvo e nunca escreve nele. |
| `phases[].fiscal` | object | sim | Mesma forma de stages.yaml:enforced_by, e resolvido pela mesma mecânica: ci_script com ::simbolo confirmado por AST, schema com arquivo real. |
| `phases[].fiscal.kind` | enum(ci_script · schema) | sim |  |
| `phases[].fiscal.ref` | string | sim |  |
| `phases[].fiscal.symbol` | string | — |  |
| `phases[].gate` | enum(none · human_approval) | sim | human_approval nas fases que escrevem julgamento ou promovem metadado. Uma fase que decide sozinha o que só um humano pode decidir é a trava que o vigiado desliga. |

## `interfaces.schema.json`

**architecture/interfaces.yaml — contratos de interface entre componentes**

> Cada interface tem um componente provedor e componentes consumidores. O fiscal cruza os símbolos expostos e as arestas com o grafo de componentes.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `interfaces` | array<object> | sim |  |
| `interfaces[].id` | string | sim |  |
| `interfaces[].name` | string | sim |  |
| `interfaces[].kind` | enum(python-api · http · event · cli) | sim |  |
| `interfaces[].provider` | string | sim |  |
| `interfaces[].consumers` | array<string> | sim |  |
| `interfaces[].exposes` | array<string> | sim |  |
| `interfaces[].status` | enum(proposed · planned · implemented · verified · deprecated) | sim |  |
| `interfaces[].derived_from` | object | — | Proveniência da ingestão: de ONDE no alvo este item foi derivado, e em QUE commit. Sem o sha, 'este metadado descreve o alvo' vira afirmação sobre um alvo que já mudou — o mesmo modo de falha que target.lock resolve, uma camada acima. ci/validate_metadata.py::check_derived_from cobra que repo casa target.repo, que sha casa target.lock exatamente e que path existe no alvo materializado. |
| `interfaces[].derived_from.repo` | string | sim |  |
| `interfaces[].derived_from.sha` | string | sim |  |
| `interfaces[].derived_from.path` | string | sim | Relativo à raiz do alvo, sem o prefixo workspace/target/. |
| `interfaces[].derived_from.section` | string | — | Âncora dentro do arquivo (título de seção, símbolo). Opcional: nem toda origem tem subdivisão. |

## `ledger.schema.json`

**Uma linha de harness/state/ledger.jsonl — evidência durável, minimizada por construção**

> ALLOWLIST ESTRUTURAL, e a formulação importa. A versão anterior deste plano prometia que 'o schema proíbe campos de identificação pessoal' — tecnicamente infactível: JSON Schema valida estrutura, não detecta PII em texto livre, e pela definição da ANPD até um handle é dado pessoal conforme o contexto. Aqui não há proibição a detectar: simplesmente NÃO EXISTE campo textual livre. Cada propriedade é hash, SHA, ID opaco, enum, timestamp, ID de CP ou referência canônica de artefato. A diferença entre 'proibido' e 'inexpressável' é a diferença entre uma regra e uma trava. E o ledger é mais estrito que business.stakeholders (que aceita handle) porque é append-only e versionado — 'de onde não se apaga', nas palavras do próprio RIPD: minimização suficiente num arquivo editável vira exposição permanente num histórico imutável.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `recorded_at` | string | sim | Instante do registro. Timestamp não é texto livre: a forma é fechada e não carrega carona. |
| `event` | enum(validation · release · adoption · ingestion · sync · attestation) | sim | Enum, nunca string: um campo 'tipo de evento' aberto seria a primeira porta por onde texto livre entraria. |
| `commit_sha` | string | sim |  |
| `result` | enum(pass · fail · unverifiable) | sim |  |
| `run_id` | string | — | ID OPACO de execução. O padrão exclui '/', ':' e espaço de propósito: sem isso, 'run_id' aceitaria uma URL, e uma URL carrega organização, repositório e às vezes autor. |
| `cp_id` | string | — |  |
| `actor_ref` | string | — | Atribuição humana PSEUDONIMIZADA, quando indispensável. O prefixo e o tamanho fixo tornam impossível escrever um login aqui. A tabela de reidentificação vive FORA deste repositório, sob controle separado — versioná-la aqui recriaria exatamente o problema que a pseudonimização resolve. |
| `findings_count` | integer | — |  |
| `findings_digest` | string | — | Digest do laudo, não o laudo. É o que permite provar 'era este o conjunto de achados' sem trazer o conteúdo — que é onde o dado pessoal do alvo auditado moraria. |
| `artifact_ref` | string | — | Referência canônica a artefato DESTE repositório. Ancorada em prefixo conhecido para que não vire caminho arbitrário — caminho arbitrário carrega nome de diretório, e nome de diretório carrega o que alguém quis chamar de alguma coisa. |
| `fiscal` | string | — | Qual fiscal produziu o registro. Padrão fechado: o conjunto de fiscais é conhecido e pequeno. |

## `privacy-review.schema.json`

**governance/privacy-review.yaml — registro tipado do julgamento de privacidade**

> O RIPD/Parecer é prosa (governance/ripd.md); ESTE arquivo é a parte fiscalizável. Separar os dois é o que permite verificar que o julgamento existe, é do tipo certo e cobre o estado atual — sem tentar fiscalizar prosa. O fiscal determinístico não julga legalidade; ele garante que o julgamento aconteceu e não está vencido.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `review` | object | sim |  |
| `review.kind` | enum(ripd_completo · parecer_proporcionalidade) | sim | Art. 38. Sistema que trata dados de titulares exige RIPD completo (8 seções); tratamento apenas incidental/efêmero admite Parecer de Proporcionalidade (4 seções). Qual dos dois é exigido é derivado do inventário pelo fiscal, não escolhido livremente. |
| `review.document` | string | sim |  |
| `review.produced_by` | enum(agent · human) | sim |  |
| `review.skill` | const(revisao-lgpd) | sim |  |
| `review.scope_fingerprint` | string | sim | Hash do escopo que o julgamento cobriu. Divergiu do escopo atual ⇒ o julgamento não fala deste sistema. Obter com: python ci/audit_lgpd.py --print-fingerprint |
| `review.issues` | array<object> | sim | Achados do julgamento, no formato da skill. P0/P1 exigem um RISK-* do registro — um issue crítico sem risco declarado é um risco não gerido. |
| `review.issues[].id` | string | sim |  |
| `review.issues[].severity` | enum(P0 · P1 · P2 · P3) | sim |  |
| `review.issues[].location` | string | sim |  |
| `review.issues[].category` | string | sim |  |
| `review.issues[].lgpd_article` | string | sim |  |
| `review.issues[].pbd_principle` | enum(Proativo e Preventivo · Privacy by Default · Privacidade no Design · Soma Positiva · Transparência · Segurança Ponta-a-Ponta · Centrado no Usuário) | sim |  |
| `review.issues[].status` | enum(open · mitigated · accepted) | sim |  |
| `review.issues[].risk` | string | — |  |
| `review.issues[].summary` | string | — |  |
| `review.issues[].consumed_by` | object | — | Para onde foi a REMEDIACAO. O issue P0/P1 ja exige um RISK-*; faltava o simetrico — um risco registrado sem trabalho declarado e um risco gerido apenas no papel. |
| `review.issues[].consumed_by.kind` | enum(change_proposal · risk · adr) | sim |  |
| `review.issues[].consumed_by.ref` | string | sim |  |
| `review.not_assessed` | array<string> | — | Categorias do checklist fora do material avaliado. Escopo honesto é requisito da skill: o que não foi visto entra aqui, nunca como 'sem achados'. |

## `project.schema.json`

**project.yaml — manifesto de identidade do projeto**

> Completa (não substitui) o pyproject.toml: propósito, domínio, criticidade, donos, governança. Legível por humano, CI e agente.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `project` | object | sim |  |
| `project.id` | string | sim |  |
| `project.name` | string | sim |  |
| `project.kind` | enum(mold · derived) | sim | mold = a casca genérica, que não governa alvo algum. derived = o gêmeo de governança de UM alvo, declarado em target. Enum fechado e obrigatório: um campo opcional aqui seria preenchido uma vez e nunca mais conferido. |
| `project.type` | string | sim |  |
| `project.lifecycle` | enum(template · incubating · active · maintenance · sunset) | sim |  |
| `project.status` | enum(active · paused · archived) | sim |  |
| `target` | object | — | O alvo que este derivado governa. DECLARA o alvo, nunca o copia: o código materializa em workspace/target/ (efêmero) no SHA de target.lock. code_roots e languages são descobertos no reconhecimento e conferidos contra o workspace — raiz declarada que não existe no alvo é achado, não detalhe. |
| `target.repo` | string | sim | owner/repo. Sem URL: o host não é decisão deste arquivo. |
| `target.ref` | string | sim | Branch acompanhada. Descoberta no alvo, nunca presumida 'main'. |
| `target.lock_source` | const(target.lock) | sim | ONDE o SHA mora — nunca o SHA. Mesma fonte única de quality_standard.version_source: duas cópias derivam e a comparação entre estados passa a mentir. |
| `target.code_roots` | array<string> | sim | Raízes de código dentro do alvo. É o universo sobre o qual a invariante do código órfão se aplica. |
| `target.test_roots` | array<string> | sim | Raízes de teste dentro do alvo. Obrigatório declarar, e lista vazia é declaração válida: 'este alvo não tem testes' é um fato sobre o alvo que a governança precisa saber, e omiti-lo o transformaria em silêncio indistinguível de 'ninguém olhou'. |
| `target.languages` | array<string> | sim | Linguagens presentes. Linguagem sem adapter cai no fallback genérico e o laudo declara o que não soube ler — nunca passa verde em silêncio. |
| `business` | object | sim |  |
| `business.domain` | string | sim |  |
| `business.purpose` | string | sim |  |
| `business.criticality` | enum(low · medium · high · critical) | sim |  |
| `business.stakeholders` | object | sim |  |
| `business.stakeholders.product_owner` | string | sim |  |
| `business.stakeholders.technical_owner` | string | sim |  |
| `business.stakeholders.security_owner` | string | sim |  |
| `quality_standard` | object | sim | Declara QUAL padrão e ONDE a versão mora — nunca o número. version_source é a fonte única (H3). |
| `quality_standard.name` | const(webqa-suite) | sim |  |
| `quality_standard.version_source` | const(requirements-qa.txt) | sim |  |
| `governance` | object | sim |  |
| `governance.default_change_mode` | const(pull_request) | sim |  |
| `governance.human_approval_required_for` | array<enum(dependency_update · production_deploy · load · active_discovery · protected_path_change)> | sim |  |
| `governance.evidence_retention_days` | integer | sim |  |
| `classification` | object | sim | Enums, não texto livre. Um campo string aberto aceita 'to-be-assessed' para sempre: nenhum fiscal consegue reprovar, e a pendência vira permanente sem nunca aparecer como falha. lgpd_relevance é cruzado com governance/data-inventory.yaml por ci/audit_lgpd.py — declarar aqui e tratar dado lá é divergência. |
| `classification.data_classification` | enum(public · internal · confidential · restricted) | sim |  |
| `classification.lgpd_relevance` | enum(none · incidental · controller · operator · controller_and_operator) | sim |  |
| `classification.internet_exposed` | boolean | sim |  |
| `classification.dpo_contact` | string | — |  |

## `protection-attestation.schema.json`

**Atestado de proteção — a camada externa da trava**

> A camada LOCAL de verificação mora no mesmo repositório que fiscaliza: um PR com privilégio suficiente remove o passo e a asserção que o vigia no mesmo commit, e o CI fica verde porque a trava saiu junto com quem reclamaria dela. Este atestado é o que quebra a circularidade — emitido por identidade externa, com obrigatoriedade configurada em ruleset administrado FORA do repositório fiscalizado. Sem essa raiz administrativa independente, a 'autoridade externa' é decorativa: quem pode mudar o workflow muda a exigência junto.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `attestation` | object | sim |  |
| `attestation.repository` | string | sim |  |
| `attestation.branch` | string | sim |  |
| `attestation.checked_at` | string | sim |  |
| `attestation.expires_at` | string | sim | Atestado sem validade seria carimbo eterno: ele afirmaria sobre uma configuração que pode ter mudado dez minutos depois. Expirado bloqueia, do mesmo modo que ausente. |
| `attestation.ruleset_ref` | string | sim | Identificação do ruleset avaliado. Referência, não cópia: o conteúdo é do lado de fora, e replicá-lo aqui criaria uma segunda versão que deriva. |
| `attestation.issuer` | object | sim | QUEM atestou. Um atestado anônimo é indistinguível de um atestado forjado — e é o próprio repositório fiscalizado que teria mais motivo para forjá-lo. |
| `attestation.issuer.identity` | string | sim |  |
| `attestation.issuer.kind` | enum(github_app · oidc_workload · external_service) | sim |  |
| `attestation.verifier_version` | string | sim |  |
| `attestation.config_digest` | string | sim | Digest da configuração avaliada. É o que permite dizer 'foi ESTA regra que passou', em vez de 'passou alguma regra num momento qualquer'. |

## `provenance.schema.json`

**Bloco de procedência do laudo**

> Carimba qual régua produziu um laudo. Obrigatório em todo artefato produzido pela suíte.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim | Versão do formato do laudo, para evolução. 1.0 = base; 1.1 = adiciona bloco artifact. |
| `artifact` | object | — | Identidade do ARTEFATO (distinta de execution.run_id, que identifica a rodada). Só válido em schema_version 1.1. |
| `artifact.kind` | string | sim |  |
| `artifact.id` | string | sim |  |
| `artifact.created_at` | string | sim |  |
| `standard` | object | sim | A régua: o padrão versionado que produziu o laudo. |
| `standard.name` | string | sim |  |
| `standard.version` | string | sim | Versão exata do padrão. 'UNINSTALLED' quando a suíte não está disponível. |
| `standard.commit` | string | sim |  |
| `standard.sensitive_paths_hash` | string | sim | SHA-256 da lista curada da suíte. Hashes divergentes na mesma versão = lista editada. |
| `consumer_project` | object | sim |  |
| `consumer_project.repository` | string | sim |  |
| `consumer_project.commit` | string | sim |  |
| `execution` | object | sim |  |
| `execution.run_id` | string | sim |  |
| `execution.mode` | enum(inventory · passive · load · active_discovery) | sim |  |
| `execution.network_used` | boolean | sim |  |
| `execution.active_gates` | array<string> | sim |  |
| `execution.runner_kind` | enum(agent · human · ci) | sim |  |
| `attestation` | object | — | Atestacao do laudo (CP-026, polimento). Reposicionada por CUSTO, nao por ser marginal: o R-09 rejeitou a justificativa de que 'os commits ja sao assinados' — eles nao sao. |
| `attestation.kind` | enum(sigstore · github_attestation) | sim |  |
| `attestation.predicate_digest` | string | sim |  |
| `attestation.issued_at` | string | sim |  |
| `attestation.bundle_ref` | string | — |  |

## `release-manifest.schema.json`

**harness/releases/vX.Y.Z.manifest.json — a raiz de confiança de uma versão do molde**

> Um derivado consome o molde POR VERSÃO, do mesmo modo que consome a régua por pin exato. Para que 'versão' signifique algo verificável, ela precisa de uma raiz de confiança que não seja a própria tag: tag é ponteiro móvel, e ponteiro móvel não ancora nada. O manifesto mora na ÁRVORE GIT do commit de release — quem move a tag não move o manifesto, e a divergência aparece. Manifesto fora da árvore, ou tag que aponta para commit sem manifesto, é ausência de release, nunca release aproximada.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `release` | object | sim |  |
| `release.repository` | string | sim | owner/repo do MOLDE. Nome de alvo nunca entra aqui: este é o repositório que publica, não o que é governado. |
| `release.tag` | string | sim | A tag desta release. O nome do arquivo é derivado dela e a igualdade é cobrada por ci/validate_metadata.py::check_release_manifests. |
| `release.commit_sha` | string | sim | O commit CUJO CONTEÚDO foi validado — o primeiro pai do commit de release. Um arquivo não pode conter o hash do commit que o contém; declarar o pai é a única forma honesta de fechar a cadeia, e o commit de release existe só para acrescentar este manifesto (ci/mold_release.py::verify_chain cobra que ele não mude mais nada). |
| `release.released_at` | string | sim |  |
| `release.validation` | object | sim |  |
| `release.validation.command` | const(python ci/validate_all.py) | sim | Um único significado de 'validado' (princípio (c) do plano). Const para que uma release não possa declarar ter sido validada por um comando mais fraco. |
| `release.validation.result` | enum(pass) | sim | Só 'pass' é representável. Um enum com 'fail' criaria a categoria 'release publicada com validação vermelha' — categoria que, existindo, será usada. |
| `release.validation.run_id` | string | sim |  |
| `release.validation.run_url` | string | — |  |
| `release.artifact_digest` | string | sim | Digest do conteúdo versionado do commit validado (git archive canônico). É o que permite dizer 'esta árvore é aquela árvore' sem confiar na tag. |

## `report.schema.json`

**Envelope do laudo**

> Envolve a procedência, o resultado e os achados. A procedência é obrigatória em qualquer comparação.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `result` | enum(ok · findings · suite_not_installed · error) | sim | ok = sem achados; findings = achados presentes; suite_not_installed = stub tolerante; error = falha. |
| `findings` | array<object> | sim | Achados já sanitizados pela suíte. Vazio quando result != findings. |
| `findings[].id` | string | sim |  |
| `findings[].severity` | enum(low · medium · high · critical) | sim |  |
| `findings[].dimension` | string | sim |  |
| `findings[].summary` | string | — |  |
| `summary` | object | — | Contagens agregadas por severidade/dimensão. Opcional. |

## `risk-register.schema.json`

**risk-register.yaml — registro de riscos que classifica a mudança antes de agir**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `risks` | array<object> | sim |  |
| `risks[].id` | string | sim |  |
| `risks[].area` | enum(webqa · dependencies · data · access · availability · governance) | sim |  |
| `risks[].description` | string | sim |  |
| `risks[].likelihood` | enum(low · medium · high · pending_judgment) | sim | pending_judgment: escrito pela ingestão, recusado em documento promovido. |
| `risks[].impact` | enum(low · medium · high · pending_judgment) | sim | pending_judgment: escrito pela ingestão, recusado em documento promovido. |
| `risks[].treatment` | enum(accept · mitigate · prevent · transfer) | sim |  |
| `risks[].owner` | string | sim |  |
| `risks[].status` | enum(open · mitigated · accepted · closed) | sim |  |
| `risks[].controls` | array<object> | sim | Referências TIPADAS. Nem todo controle é arquivo local: o gate mora na suíte externa, o ambiente no GitHub. |
| `risks[].controls[].kind` | enum(local_path · standard_symbol · pinned_dependency · github_environment · branch_protection) | sim |  |
| `risks[].controls[].ref` | string | sim |  |
| `risks[].controls[].standard` | const(webqa-suite) | — |  |
| `risks[].controls[].version_source` | string | — | Arquivo que trava a versao do artefato externo. Para standard_symbol e sempre requirements-qa.txt (fonte unica da regua). Para pinned_dependency e o arquivo onde o pin daquela dependencia mora, tipicamente pyproject.toml ou um requirements-*.txt. |
| `risks[].controls[].dependency` | string | — | Nome do pacote, como ele aparece em security/dependencies.yaml. E o elo que faz o controle ser reconferivel: o inventario diz de onde a dependencia vem e com que pin. |
| `risks[].derived_from` | object | — | Proveniência da ingestão: de ONDE no alvo este item foi derivado, e em QUE commit. Sem o sha, 'este metadado descreve o alvo' vira afirmação sobre um alvo que já mudou — o mesmo modo de falha que target.lock resolve, uma camada acima. ci/validate_metadata.py::check_derived_from cobra que repo casa target.repo, que sha casa target.lock exatamente e que path existe no alvo materializado. |
| `risks[].derived_from.repo` | string | sim |  |
| `risks[].derived_from.sha` | string | sim |  |
| `risks[].derived_from.path` | string | sim | Relativo à raiz do alvo, sem o prefixo workspace/target/. |
| `risks[].derived_from.section` | string | — | Âncora dentro do arquivo (título de seção, símbolo). Opcional: nem toda origem tem subdivisão. |
| `risks[].related` | array<string> | — | Ativos que este risco cobre: capacidades, componentes, interfaces, superfícies e requisitos. É a aresta que torna a cobertura reversa verificável — sem ela só se sabe que o controle existe, nunca que o ativo é vigiado por alguém. |
| `risks[].due` | string | — | Prazo do tratamento. Exigido quando status é open: risco aberto sem prazo é risco aceito sem ninguém ter aceitado — dura para sempre e nunca aparece como pendência. |
| `risk_exemptions` | array<object> | sim | Ativos que deliberadamente NÃO precisam de risco associado. Mesma mecânica de stages.yaml:ungoverned, incluindo a propriedade que a torna honesta: isenção que não casa ativo algum é ela própria um achado — do contrário a lista vira o lugar onde a cobertura é fingida com uma linha. |
| `risk_exemptions[].ref` | string | sim |  |
| `risk_exemptions[].justification` | string | sim |  |

## `stages.schema.json`

**harness/stages.yaml — as etapas do projeto e seus fiscais**

> Índice das etapas, não uma segunda descrição do projeto. Referencia artefatos por CAMINHO e fiscais por caminho/símbolo; restatar um ID (CAP-, REQ-, CMP-...) aqui criaria uma segunda fonte de verdade, e o schema recusa estruturalmente.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `stages` | array<object> | sim |  |
| `stages[].id` | string | sim |  |
| `stages[].order` | integer | sim |  |
| `stages[].name` | string | sim |  |
| `stages[].artifacts` | array<—> | sim |  |
| `stages[].enforced_by` | array<—> | sim |  |
| `stages[].privacy_lens` | object | sim | A lente de LGPD desta etapa. scan:true põe os artefatos na superfície varrida por ci/audit_lgpd.py — a superfície é declarada uma vez, nunca hard-coded no fiscal. |
| `stages[].privacy_lens.scan` | boolean | sim |  |
| `stages[].privacy_lens.question` | string | sim |  |
| `ungoverned` | array<object> | sim | Arquivos deliberadamente fora de qualquer etapa. A isenção é declarada com motivo, nunca tácita — e uma isenção que não casa nada é isenção morta. |
| `ungoverned[].path` | — | sim |  |
| `ungoverned[].justification` | string | sim |  |

## `target-lock.schema.json`

**target.lock — fonte única do SHA do alvo**

> Análogo exato de requirements-qa.txt: aquele fixa a versão da régua, este fixa a versão do alvo. project.yaml declara QUAL alvo (repo, ref) e ONDE o SHA mora (target.lock); o número mora só aqui. Sem essa separação, 'o metadado descreve o alvo' vira afirmação sobre um alvo que já mudou, e o drift fica invisível em vez de detectável.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `kind` | enum(mold · derived) | sim | Espelha project.yaml:project.kind. ci/validate_metadata.py::check_target_lock cobra a igualdade — dois arquivos que discordam sobre o papel do repositório são pior que um só. |
| `target_sha` | string | null | sim | Commit exato do alvo ingerido. null no molde, que não governa alvo algum. |
| `mold_release` | object | null | — | De QUAL versão do molde este derivado nasceu. Simétrico a target_sha uma camada acima: aquele ancora o alvo governado, este ancora a carcaça que governa. A tag sozinha não bastaria — tag é ponteiro móvel, e um consumidor que cita só a tag afirma ter nascido de um conteúdo que pode ter sido reescrito depois. manifest_sha é o que torna isso detectável. |
| `mold_release.repository` | string | sim |  |
| `mold_release.tag` | string | sim |  |
| `mold_release.commit_sha` | string | sim | O commit do molde cujo conteúdo foi validado; igual ao release.commit_sha do manifesto, e ci/mold_release.py::verify_chain cobra a igualdade. |
| `mold_release.manifest_path` | string | sim | Derivado da tag, nunca escolhido: caminho livre permitiria duas releases no mesmo arquivo, e a segunda venceria em silêncio. |
| `mold_release.manifest_sha` | string | sim | sha256 dos BYTES canônicos do manifesto. É o elo que detecta tag movida: o hash do manifesto no novo destino não confere com o que foi consumido. |

## `threat-model.schema.json`

**security/threat-model.yaml — ameaças por componente e interface, com residual rastreável**

> Segurança deixa de ser difusa e vira departamento. Duas travas estruturais definem o arquivo: toda ameaça exige ao menos uma mitigação (referência TIPADA, mesma forma dos controls[] do risk-register) e um residual_risk apontando para um RISK-* real. Ameaça catalogada e não tratada é o 'to-be-assessed' do ADR-002 vestido de diligência: parece trabalho de segurança e não obriga a nada. Com residual_risk, a ameaça herda dono, prazo e a cobertura reversa de R2.

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `threats` | array<object> | sim |  |
| `threats[].id` | string | sim |  |
| `threats[].stride` | enum(spoofing · tampering · repudiation · information_disclosure · denial_of_service · elevation_of_privilege) | sim | Enum fechado de propósito: categoria livre aceita 'outros' para sempre, e ninguém consegue perguntar 'quais ameaças de elevação de privilégio existem?'. |
| `threats[].target` | string | sim | O que é ameaçado: um componente, interface ou superfície do sistema governado, ou uma ETAPA do harness (STAGE-*) quando o ameaçado é a própria máquina de governar. Resolvido por ci/validate_metadata.py::check_threat_model — ameaça contra alvo inexistente é trava que não encontra o que vigiar. A segunda namespace existe porque apontar uma ameaça ao harness para um componente de negócio qualquer satisfaz o fiscal sem dizer nada verdadeiro. Referência por ID, nunca por caminho: o artefato vigiado continua sendo o mesmo onde quer que o arquivo passe a morar (CP-029). |
| `threats[].attack_vector` | string | sim |  |
| `threats[].severity` | enum(low · medium · high · critical · pending_judgment) | sim | pending_judgment: nenhuma ferramenta decide gravidade de ameaça. Recusado em documento promovido pela mesma trava da Fase D. |
| `threats[].mitigations` | array<object> | sim | Referências TIPADAS, mesma forma de risk-register:controls[]. minItems 1 é a trava: ameaça sem mitigação é catálogo, não modelo. |
| `threats[].mitigations[].kind` | enum(local_path · standard_symbol · github_environment · branch_protection · accepted) | sim |  |
| `threats[].mitigations[].ref` | string | sim |  |
| `threats[].mitigations[].standard` | const(webqa-suite) | — |  |
| `threats[].mitigations[].version_source` | const(requirements-qa.txt) | — |  |
| `threats[].residual_risk` | string | sim | O que sobra depois das mitigações, ancorado num risco real. É o que faz a ameaça herdar dono, prazo e a cobertura reversa da Fase E em vez de morrer num arquivo próprio. |

## `ui-surfaces.schema.json`

**ui-surfaces.yaml — superfícies de UI ligadas a capacidades**

> Critérios de experiência que precisam sobreviver a mudanças no código. Cada superfície aponta para uma capacidade (CAP-*).

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `ui_surfaces` | array<object> | sim | Lista vazia é declaração VÁLIDA: um alvo sem interface — biblioteca, CLI, worker — precisa poder dizer 'não tenho UI'. Proibir de declará-lo transformaria o fato em silêncio indistinguível de 'ninguém olhou', pelo mesmo raciocínio de target.test_roots. A regra R3 do alinhamento segue mordendo sobre as superfícies que existirem. |
| `ui_surfaces[].id` | string | sim |  |
| `ui_surfaces[].capability` | string | sim |  |
| `ui_surfaces[].status` | enum(proposed · planned · implemented · verified · deprecated) | sim |  |
| `ui_surfaces[].routes` | array<string> | sim |  |
| `ui_surfaces[].primary_user_goal` | string | sim |  |
| `ui_surfaces[].acceptance_criteria` | array<string> | sim |  |
| `ui_surfaces[].satisfies` | array<string> | — |  |
| `ui_surfaces[].derived_from` | object | — | Proveniência da ingestão: de ONDE no alvo este item foi derivado, e em QUE commit. Sem o sha, 'este metadado descreve o alvo' vira afirmação sobre um alvo que já mudou — o mesmo modo de falha que target.lock resolve, uma camada acima. ci/validate_metadata.py::check_derived_from cobra que repo casa target.repo, que sha casa target.lock exatamente e que path existe no alvo materializado. |
| `ui_surfaces[].derived_from.repo` | string | sim |  |
| `ui_surfaces[].derived_from.sha` | string | sim |  |
| `ui_surfaces[].derived_from.path` | string | sim | Relativo à raiz do alvo, sem o prefixo workspace/target/. |
| `ui_surfaces[].derived_from.section` | string | — | Âncora dentro do arquivo (título de seção, símbolo). Opcional: nem toda origem tem subdivisão. |

## `vision.schema.json`

**business/vision.yaml — visão de produto e métricas de sucesso**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `schema_version` | string | sim |  |
| `metadata_version` | string | sim |  |
| `source_of_truth` | boolean | sim |  |
| `generated_from` | string | null | — |  |
| `product` | object | sim |  |
| `product.problem` | string | sim |  |
| `product.target_users` | array<string> | sim |  |
| `product.value_proposition` | string | sim |  |
| `product.success_metrics` | array<object> | sim |  |
| `product.success_metrics[].id` | string | sim |  |
| `product.success_metrics[].description` | string | sim |  |
| `product.success_metrics[].target` | string | sim |  |

