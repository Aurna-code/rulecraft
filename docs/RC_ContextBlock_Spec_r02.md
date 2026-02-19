# Rulecraft ContextBlock Spec — r02 (Selective Context Injection)

- 버전: r02
- 작성일: 2026-02-10 (Asia/Seoul)
- 수정일: 2026-02-18 (Asia/Seoul)
- 패치:
  - hotfix14 — ContextBlock(선택적 주입 단위) + L2-Applicability/SieveGenPlan 연결
  - hotfix14p4 — 운영 최소 계약(context_select.version + 불변식 위반 처리) 정리
  - hotfix14p5 — Offline NavigatorGraph(오프라인) + HotPathBudget 상한 + early-exit(초기 디폴트)
  - hotfix14p7(2601.22401) — IntentSatisfaction(meaningful correctness) + ProvenanceProbe(prior-art/출처) 신호 추가
  - hotfix14p8(base) — 운영 정합성 최소 계약(의도/선행 힌트의 의미 고정 + Intent-first/오염 방지 게이트 연결) 명문화
  - hotfix14p9 — Verification gap(UNKNOWN) 명문화 + Canary/rollback 프로토콜 구체화 + ContextBlock conflict 결정적 처리 규율
  - ENCOMPASS(2512.03571) — ContextBlock Plan Search(EPS branchpoint): 주입 계획을 작은 빔으로 탐색(옵션) 추가
  - Categorical Flow Maps(2602.12233) — 범주형 정책/개입 분포를 few-step 추정기로 증류 + test-time guidance(옵션)
  - CL-bench(2602.03587) — Context Learning 태그/힌트 + '컨텍스트 우선' ContextBlock + CLPack v1 루브릭(결정적 assert로 내려가기) 템플릿 추가(옵션)
  - Reasoning Failures Survey(2602.06176) — rf_* 태그 규약 + ROBUSTNESS(transform) 연동 힌트 추가
  - TKDE DataPrep Survey(2601.17058) — DataPrep(정리/통합/보강) ContextBlock 태그/힌트 템플릿 추가

> 목적: Rulecraft의 룰/정책/메모리/PRAXIS 전술을 “질의별로 필요한 조각만” 주입할 수 있게 **원자 단위(ContextBlock, ContextBlock)** 로 정규화한다.
> 계약(SSOT optional): `RC_Contracts_SSOT_ssot10.md` 의 `ContextBlock`, `SieveGenPlan`, `SieveExample`

---

## 0) TL;DR
- CU는 “규칙 한 개 / 정의 한 개 / 예외 한 개 / 전술 한 개” 같은 **원자 문장**을 담는다.
- Router는 q에 대해 ContextBlock 후보를 **L0(cheap) → L2(optional)** 순으로 좁혀서 “필요한 것만” 주입한다.
- 오프라인에서는 SieveGenPlan로 `(q, applicable ContextBlock)` 데이터를 만들고 회귀팩/증류에 투입한다.
- CU는 **데이터 타입**이지, “정책 변화”가 아니다. 정책/가중치 변화는 항상 replay→canary→rollback.

---

## 1) ContextBlock 스키마(요약)


(SSOT 발췌, optional extension)
```yaml
ContextBlock:
  schema_version: "0.1.0"
  context_id: string                     # MUST (안정적 ID)
  text: string                      # MUST (원문, 원자 규칙/정의/지침 1개)
  tags: [string]|null               # MAY
  priority: int|null                # MAY
  conflicts_with: [string]|null     # MAY
  source_ref: string|null           # MAY
  applicability_hints: object|null  # MAY
```

예시(권장, YAML):
```yaml
schema_version: "0.1.0"
context_id: "cb_format_json_only_v1"
text: "출력은 오직 JSON만. JSON 외 텍스트(설명/머리말/꼬리말) 금지."
tags: ["stage:verify","risk:hallucination"]
priority: 50
conflicts_with: ["cb_allow_explanations_v1"]
source_ref: "policy:output_format"
applicability_hints:
  must_have: ["json_only"]
  regex_any: ["\\bJSON\\b", "schema"]
```

## 1.1 ContextPacker(렌더러) 원칙 — “저장”과 “주입”을 분리한다

- `ContextBlock`은 **저장 포맷(권장: YAML)**을 SSOT로 고정한다.
- 런타임 주입은 `ContextPacker/Renderer`가 담당한다:
  - 모델/런타임(로컬/프론티어)과 `access_mode`에 따라 `prompt_embed`용 압축 렌더링을 만들거나,
  - `file_native`일 땐 “검색 가능한 앵커(헤더/키/ID)” 중심으로 파일 탐색을 돕는다.
- 같은 내용을 “저장용 문서”와 “주입용 텍스트”로 이중 관리하지 않는다(드리프트 방지).

## 1.2 (선택) NavigatorUnit — 디스앰비규에이션/색인 ContextBlock

`NavigatorUnit`은 “어디를 봐야 하는지”를 안내하는 얇은 CU다.
다중 파일/도메인 파티셔닝을 쓸수록 중요해진다.

- 목적: 애매한 용어/동의어/우선순위/참조 순서를 고정해서, 포맷/검색 꼼수 대신 **규칙으로** 해결한다.
- 권장 필드(가이드):
  - `kind: "navigator"`
  - `entries[]: { key, desc, pointers[], grep_hints[], must_have[]?, intent_hints[]?, prior_art_hints[]? }`
  - `pointers[]: { ref_type, ref }`  (예: rule_pack / context_id / doc_section)

  - (옵션) `must_have[]`: 이 key로 유입되는 태스크가 **반드시 포함해야 하는 산출물 슬롯/요구**(IntentSatisfaction용)
    - 예: `"diff_patch"`, `"citations"`, `"table"`, `"json_only"`
  - (옵션) `intent_hints[]`: 의도 판정/슬롯 추출을 돕는 힌트(키워드/정규식/간단 예시)
  - (옵션) `prior_art_hints[]`: 선행/출처 탐침(ProvenanceProbe)의 쿼리 토큰(용어/동의어/약어)

#### 운영 정합성 — NavigatorUnit 필드의 의미(의도/선행)

NavigatorUnit의 `must_have/intent_hints/prior_art_hints`는 “설명용 메모”가 아니라,
Validator/Router가 **일관된 신호**를 내기 위한 최소 계약으로 취급한다.

- `must_have[]`:
  - IntentSatisfaction(L2a)가 “요청 산출물 슬롯”을 판정할 때 쓰는 기준이다.
  - 산출물에서 must_have 슬롯이 누락되면 Validator는 `INTENT:PARTIAL` 또는 `INTENT:NOT_SATISFIED`를 `violated_constraints`에 기록하는 것을 권장한다.
- `intent_hints[]`:
  - L0(cheap) 슬롯 추출/의도 분해를 돕는다. 힌트는 “강제 규칙”이 아니라 **후보 압축 힌트**다.
- `prior_art_hints[]`:
  - ProvenanceProbe(L2.5)의 쿼리 토큰이다. 기본은 hot-path에서 OFF이며, probe/full에서만 제한적으로 사용한다.

런타임 권장 흐름:
1) NavigatorUnit으로 “도메인/파일”을 좁힘
2) 일반 CU로 “주입 조각”을 좁힘(`context_select`)
3) 최종 주입
SSOT의 `ContextBlock`을 따른다.

권장 해석:
- `context_id`: 절대 바꾸지 말아야 하는 안정 키(집계/회귀/충돌표의 기준)
- `text`: 원문(프롬프트에 그대로 들어갈 수 있어야 함)
- `tags`: cheap filter용 라벨(예: `tool:web`, `domain:finance`, `stage:router`)
- `priority`: 상충 시 tie-breaker(높을수록 우선)
- `conflicts_with`: 명시 상충 목록(가능하면 작은 집합으로 유지)
- `applicability_hints`: 키워드/슬롯/정규식 등 “모델 없이” 후보를 줄이는 힌트


### 1.2.1 Offline NavigatorGraph(오프라인) — KG 기반 NavigatorUnit 보강(옵션)

NavigatorUnit을 사람이 계속 손으로 유지하면, 팩/문서가 커질수록 “찾기/이름짓기/동의어” 비용이 기하급수로 늘어난다.
그래서 **런타임에 무거운 그래프 인덱스를 붙이지 않고**, 오프라인 분석기로 NavigatorUnit을 보강하는 흐름을 권장한다.

- 입력(권장): (a) ContextBlock(tags/hints/pointers), (b) 설계 문서 섹션/앵커, (c) RunLog의 `grep_tax`/실패 클러스터, (d) 룰팩 메타
- 처리(예시): 텍스트→트리플 추출→그래프 구축→연관 섹션/룰/팩 후보를 `pointers/grep_hints`로 제안
- 출력(권장): NavigatorUnit 패치(추가/수정; pointers/grep_hints뿐 아니라 must_have/intent_hints/prior_art_hints 제안 포함) + “검색 실패 상위 키워드” 리포트
- 운용 규율(MUST):
  - 오프라인에서만 실행한다(런타임에는 정적 NavigatorUnit만 로드).
  - 자동 제안은 PR/리뷰 단위로만 반영한다(rollback 가능해야 함).


---

## 2) 분해(Decompose) 규칙 — 실무 가이드

### 2.1 원자성 기준
- 한 CU는 “하나의 행동 제약”만 담아라.
  - ✅ “웹 검색은 필요할 때만 사용하고, 출처를 남겨라.”
  - ❌ “웹 검색/파일 검색/도구 사용/출력 포맷/예외 처리…”를 한 CU에 몰아넣기

### 2.2 충돌(conflict) 작성 기준
- 충돌은 **명시적으로 관리 가능한 것만** 적어라.
- 충돌표가 커지면 유지비가 폭발하므로:
  - (1) 태그+우선순위로 대부분 해결
  - (2) 정말 위험한 상충만 `conflicts_with`에 박기

(권장) 충돌/우선순위의 결정적 처리 규율
- 목표: 같은 입력에서 ContextBlock 선택 결과가 구현/환경에 따라 흔들리지 않게 한다(회귀/클러스터 분석 가능성).
- 권장 규칙:
  1) 후보 정렬: `priority desc` → `context_id asc`(안정 tie-breaker)
     - priority가 없으면 0으로 간주
  2) 선택: 정렬된 순서로 스캔하며, 이미 선택된 CU와 충돌하면 skip
     - 충돌 판정은 `conflicts_with`를 기준으로 하되, 구현은 “대칭(symmetric)으로 취급”하는 것을 권장
  3) 기록: skip된 CU는 `RunLog.context_select.conflict_pruned_context_ids`에 남긴다(관측 가능성)
- 주의: 이 규칙은 “정답”이 아니라 운영 안정성 규율이다. 다른 알고리즘을 쓰더라도
  (a) 결정적이어야 하고 (b) pruned 목록을 로그로 남겨야 한다.

### 2.3 태그(tag) 최소 세트(권장)
- `domain:*`        (예: `domain:math`, `domain:repo`)
- `tool:*`          (예: `tool:web`, `tool:file_search`)
- `stage:*`         (예: `stage:router`, `stage:verify`, `stage:compose`)
- `risk:*`          (예: `risk:cost`, `risk:hallucination`)

- (data_prep 권장 확장) 데이터 준비 작업에서 cheap filter를 돕는 태그 예시:
  - `domain:data_prep`
  - `dp_task:cleaning|integration|enrichment`
  - `dp_granularity:record|schema|object` (SSOT의 `score_evidence.data_prep.granularity` 권장값과 정렬)
  - (옵션) `dp_scope:cell|row|column|table|dataset` (더 세밀한 작업 스코프 라벨)
  - `dp_subtask:standardization|error_processing|imputation|entity_matching|schema_matching|annotation|profiling`

- (2602.06176 권장 확장) **Reasoning Failure 태그** — “어떤 추론에서 / 어떤 종류로” 흔들리는지 CU에 라벨링
  - `rf_reasoning:*`  (예: `rf_reasoning:formal`, `rf_reasoning:informal`, `rf_reasoning:embodied`)
  - `rf_failure:*`    (예: `rf_failure:fundamental`, `rf_failure:limitation`, `rf_failure:robustness`)
  - `rf_topic:*`      (예: `rf_topic:reversal_curse`, `rf_topic:compositional`, `rf_topic:distractor_sensitivity`)


- (2602.03587 권장 확장) **Context Learning 태그** — “컨텍스트로부터 무엇을 학습/적용해야 하는지” 라벨링
  - `cl_cat:domain_knowledge|rule_system|procedure|empirical_discovery`
  - `cl_flag:prior_conflict`     (컨텍스트가 사전지식과 충돌하도록 설계됨)
  - `cl_flag:multiturn`          (동일 컨텍스트 내 task 의존성 있음)
  - `cl_flag:rubric_eval`        (verification rubrics 존재/사용)

### 2.4 (data_prep 권장) applicability_hints 슬롯 예시 — “전역 제약/근거”를 빠르게 찾기

data_prep 계열은 “어떤 CU를 넣었어야 했나?”가 비교적 명확하다. 따라서 힌트를 표준화하면,
L0(cheap)만으로도 후보를 꽤 잘 줄일 수 있다.

예시:
```yaml
applicability_hints:
  dp_task_any: ["cleaning", "integration"]          # 또는 enrichment
  dp_granularity_any: ["record", "schema"]          # record(=row/cell) / schema / object(=entity) 중
  dp_scope_any: ["row", "column"]                   # (옵션) 더 세밀한 스코프
  requires_global_view: true                        # 전역 통계/제약(유니크/분포/참조무결성) 필요 가능성
  invariants: ["symmetry", "transitivity"]          # integration에서 자주
  must_use_tools: ["tool:sandbox"]                  # L3 하네스/통계 계산/코드 실행
```

메모:
- 이 필드는 SSOT를 바꾸지 않는다(`object|null` 자유 payload).
- Router는 `requires_global_view=true`를 보면, 핫패스에서 “표 전체를 프롬프트에 넣기” 대신 SandboxProbe/L3로 우회하는 정책을 걸기 쉽다.
- 이 태그/힌트들은 “정답 판정”이 아니라 **라우팅/주입 힌트**다.
- FlowMap/회귀팩 집계 키는 여전히 `failure_cluster_id`/`violated_constraints` 중심으로 유지한다.
---

### 2.5 (CL-bench 권장) applicability_hints 슬롯 예시 — “컨텍스트 우선/사전지식 충돌/루브릭” 라우팅 힌트

context learning 계열 태스크는 “무엇을 주입해야 하는지”가 비교적 분명하다(규칙 시스템/절차/데이터 법칙 등).
따라서 L0(cheap)에서 tags/hints로 후보를 줄이고, (필요할 때만) Validator의 `L2-ContextLearningProbe`를 승격 트리거로만 쓰는 구성이 가성비가 좋다.

예시:
```yaml
applicability_hints:
  context_learning: true
  cl_category_any: ["rule_system", "procedure"]   # 또는 domain_knowledge / empirical_discovery
  prior_conflict_expected: true                   # 사전지식과 충돌하도록 설계된 컨텍스트
  multiturn: true                                 # task 의존성
  rubrics_available: true                         # verification rubrics 존재
  must_disable_tools: ["tool:web"]                # “컨텍스트만으로 풀기” 레일이면 명시
```

메모(오염 방지):
- `prior_conflict_expected=true`인 컨텍스트는 fiction/modified knowledge일 가능성이 높다.
  - 이런 컨텍스트에서 나온 “규칙/사실”을 전역 Rulebook/Memory로 승격하면 자기오염이 된다.
  - 기본 정책은 run-local(WorkingSet)에서만 쓰고, 승격은 금지(또는 HumanGate)로 둔다.


## 3) 런타임 적용: L0 → L2-Applicability

### 3.1 L0(cheap) 후보 추리기
- 입력: q, tags/힌트, 최근 failure_cluster 신호
- 출력: ContextBlock 후보 top-N
- 목표: “L2가 애매한 것만” 보도록 만드는 것(비용/안정성)

### 3.2 L2-Applicability(선택)
- Validator r08의 §3.2.3을 따른다.
- 출력은 SSOT 변경 없이 `ValidationResult.score_evidence.applicability`에 기록한다.
- 적용성 애매 시 `reason_codes`에 `applicability_unknown`(옵션) + should_escalate로 승격.


### 3.2.1 (옵션) ContextBlock Plan Search — 주입 계획을 작은 빔으로 탐색(EPS branchpoint)

기본(hot-path)은 기존처럼 **결정적 context_select**(priority/충돌 처리)로 끝낸다.
다만 should_escalate이 켜지고, overinject/충돌/적용성 애매가 반복되는 버킷에서는
`router:context_select`를 branchpoint로 보고 “주입 계획(injection plan)”을 소규모로 탐색할 수 있다.

권장 방식(현실 버전):
- 후보: 동일한 `candidate_context_ids`에서 시작하되,
  - unknown_context_ids의 포함/제외,
  - 동급 priority에서의 조합,
  - must_have 슬롯 충족( NavigatorUnit.must_have ) 우선
  같은 “안전한 변형”만 만든다.
- 각 계획은 반드시 기존의 **결정적 conflict pruning 규칙을 통과**해야 한다(충돌을 탐색으로 풀지 않는다).
- 각 계획에 대해 짧은 1-pass를 실행하고, L1(형식/제약) + (가능하면) L3로 검증해서
  `ValidationResult.score`가 높은 계획을 선택한다.

로깅(권장):
- 최종 선택된 plan은 기존처럼 `RunLog.context_select.*`에 남긴다.
- 탐색 중 버린 plan들은 SSOT의 `SearchNodeRecord`(옵션) 또는 `tree_search.node_store_ref`로만 남기고,
  RunLog에는 “최종 plan”만 남겨 로그 폭발을 막는다.



---



### 3.3 (옵션) Categorical Flow Maps(2602.12233)로 context_select를 “few-step policy”로 증류

Selective Context Injection의 핵심 병목은 “좋은 CU를 찾는 것”보다,
**(a) 후보가 너무 많아지는 overinject** 와 **(b) 상충(conflict)로 인한 불안정** 이다.
`L0→L2` 파이프라인이 기본이지만, 로그가 충분히 쌓이면 context_select도 사실상 “범주형 의사결정”이므로
arXiv:2602.12233 *Categorical Flow Maps* 계열로 **정책 힌트 모델**을 만들 수 있다.

권장 접근(현실 버전):
- ContextBlock 개별 id를 바로 분류/생성하지 말고, 먼저 **ContextBlock 팩(pack)/플랜(plan)** 을 정의한다.
  - 예: `"pack:web_tools"`, `"pack:math_verify"`, `"pack:security_guard"`, `"pack:writer_style"`
- 런타임은 `pack_id → context_id[]`로 풀어서 주입하고, 기존 conflict pruning(`conflicts_with`)을 그대로 적용한다.
- 즉, 모델은 “팩 선택”만 하고, 최종 주입은 **결정적 규칙**으로 마무리한다.

학습 데이터(오프라인):
- 입력 x: `bucket_id` + 질의 임베딩/슬롯 + `NavigatorUnit` 힌트 + (가능하면) L0 top-N 후보 통계
- 라벨 y: 과거 로그의 `context_select.injected_context_ids`를 “팩”으로 리매핑한 `pack_id` (또는 top-1/top-2)

test-time guidance(옵션):
- 목적 함수가 바뀌는 상황(예: 예산 타이트, 오염 민감, high impact)에서,
  팩 확률을 token_cost/충돌 리스크로 재가중(reweight)해 “작고 안전한 팩”을 우선하게 만들 수 있다.
- 단, guidance 파라미터(β)와 reward 정의는 정책이므로 replay→canary로만 고정한다(런타임 즉흥 변경 금지 권장).

운영 규율:
- 기본은 OFF. 붙여도 **hint**로만 쓰고, 불변식은 항상 강제한다:
  - `injected_context_ids ⊆ candidate_context_ids` (SSOT/Playbook의 context_select 불변식)
  - conflict 위반 시 결정적 규칙으로 제거 + `context_conflict_detected`/`context_select_invariant` 로깅
- 로깅은 SSOT를 깨지 않도록 `run_tags`로 남긴다.
  - 예: `run_tags += ["context_hint:cat_flow_map_v1","context_pack:math_verify","guide:beta0.2"]`


## 4) 오프라인: SieveGenPlan로 회귀팩 만들기

- seed: 실패 클러스터 대표 q + ContextBlock seed 조합
- generate: ContextBlock seed가 “적용되는” 질의 q' 합성
- verify: 적용 CU만 남겨 `SieveExample` 기록
- use: Distiller/RegressionPack/PatterningPlan의 probe로 투입
- 규율: 항상 replay→canary→rollback


### 4.0a (data_prep 예시) ContextBlock 템플릿 — “표 전체를 넣지 말고, 전역 신호를 계산하라”

아래는 data_prep(정리/통합/보강) 작업에서 자주 반복되는 “안전 ContextBlock” 예시다.
(문장 1개=ContextBlock 1개 원칙 유지)

```yaml
# 1) 전역 신호 우선(샘플+통계) — 로컬 문맥만으로 표를 ‘지어내며’ 고치는 걸 방지
schema_version: "0.1.0"
context_id: "cb_dp_global_stats_first_v1"
text: "대규모 테이블은 전체를 프롬프트에 넣지 말고, 샘플 + 전역 통계(null/unique/분포/타입)를 SandboxProbe로 계산해 그 결과만 주입한다."
tags: ["domain:data_prep","dp_task:cleaning","tool:sandbox","risk:cost"]
applicability_hints: {requires_global_view: true}

# 2) 결측값/보강은 ‘근거 없으면 보류’
schema_version: "0.1.0"
context_id: "cb_dp_no_hallucinated_imputation_v1"
text: "결측값(imputation)이나 프로파일(enrichment)은 근거가 없으면 임의 값을 생성하지 말고 NULL/UNKNOWN으로 남기거나 근거(유사 tuple/쿼리/외부 출처)를 먼저 확보한다."
tags: ["domain:data_prep","dp_task:enrichment","risk:hallucination","stage:verify"]

# 3) 매칭 불변식(대칭/추이) 강제
schema_version: "0.1.0"
context_id: "cb_dp_integration_invariants_v1"
text: "entity/schema matching은 대칭성(match(A,B)=match(B,A))과(클러스터면) 추이성(A~B,B~C⇒A~C)을 불변식으로 두고, 깨지면 FAIL/UNKNOWN으로 처리한다."
tags: ["domain:data_prep","dp_task:integration","risk:robustness","stage:verify"]
applicability_hints: {invariants: ["symmetry","transitivity"]}

# 4) 변환은 diff+rollback 가능해야 한다
schema_version: "0.1.0"
context_id: "cb_dp_transform_must_be_replayable_v1"
text: "데이터 정리는 (a) 적용 범위, (b) before/after 예시, (c) 재실행 가능한 변환(pandas/sql/regex) 형태로 제안하고, 되돌리기(rollback) 가능한 단위로 쪼갠다."
tags: ["domain:data_prep","dp_task:cleaning","risk:irreversible_change","tool:sandbox"]
```

---

### 4.0b (context_learning 예시) ContextBlock 템플릿 — “컨텍스트 우선 + 루브릭 체크 + 멀티턴 상태”

```yaml
# 1) 컨텍스트 우선: 사전지식과 충돌해도 컨텍스트를 따른다
schema_version: "0.1.0"
context_id: "cb_cl_context_is_ground_truth_v1"
text: "이 태스크는 컨텍스트에 포함된 신규 지식/규칙을 따라야 한다. 일반 상식/사전지식과 충돌해도 컨텍스트를 우선한다."
tags: ["stage:compose","risk:hallucination","cl_flag:prior_conflict"]
applicability_hints: {context_learning: true, prior_conflict_expected: true}

# 2) 루브릭 체크리스트: 제출 전 누락 점검
schema_version: "0.1.0"
context_id: "cb_cl_rubric_checklist_before_submit_v1"
text: "제출 전에 제공된 rubrics(요건 리스트)를 체크리스트로 훑고, 누락된 요건을 보완한다. 근거가 없으면 'UNKNOWN'으로 남긴다."
tags: ["stage:verify","cl_flag:rubric_eval"]

# 3) 멀티턴 의존성: 이전 turn 산출과 모순 금지
schema_version: "0.1.0"
context_id: "cb_cl_multiturn_state_consistency_v1"
text: "같은 컨텍스트 내 멀티턴에서는 이전 turn의 산출/가정과 모순되지 않도록 WorkingSet에 요약(상수/정의/결론)을 유지하고, 충돌 시 먼저 정합성을 해결한다."
tags: ["stage:compose","cl_flag:multiturn","risk:robustness"]
applicability_hints: {multiturn: true}
```

### 4.0c (CLPack v1 예시) Rubric ContextBlock 템플릿 — 루브릭을 결정적 회귀(assert)로 내리기

CLPack의 관건은 “루브릭을 잘 쓰는 것”이 아니라, **루브릭을 자동 채점(assert)으로 환원**하는 것이다.
따라서 루브릭 항목은 가능하면 함수명/토큰/파라미터명/금지 문자열처럼 *검사 가능한 표면*을 포함해야 한다.

(참조; 안정 키) Validator는 루브릭/CLPack 실패를 아래 `violated_constraints` 키로 표준화해 남긴다(SSOT §5.2.4).
- `CONTEXT_LEARNING:NOT_LEARNED`
- `CONTEXT_LEARNING:PRIOR_KNOWLEDGE_OVERRIDE`
- `CONTEXT_LEARNING:INCOMPLETE`
- `CONTEXT_LEARNING:TURN_DEPENDENCY_BROKEN`


권장 패턴: 루브릭을 별도 artifact로 저장하되, CU에도 “검사 힌트”를 object payload로 남겨 Router/Validator/팩 생성기가 재사용하게 한다.

```yaml
# 루브릭(요건) 스펙을 CU로 남기는 예시 — 구현은 자유, 핵심은 deterministic로 내려갈 수 있게 만드는 것
schema_version: "0.1.0"
context_id: "cb_cl_rubric_spec_v1"
text: |
  Rubrics(요건):
  - [required_token] Safety_request_airspace( 를 반드시 사용
  - [forbidden_token] DroneAirspace_access 는 사용 금지
  - [required_params] 출력 JSON에 flight_zone, landing_site 필수
  - [tool_forbidden] web 툴 호출 금지(컨텍스트만으로 풀기)
  - [multiturn] 다음 turn에서 이전 result_id를 재사용

tags: ["stage:verify","cl_flag:rubric_eval","cl_cat:rule_system"]
applicability_hints:
  context_learning: true
  rubrics_available: true

  # (팩 생성기/Validator가 그대로 가져다 쓰는 검사 힌트)
  must_use_tokens: ["Safety_request_airspace("]
  forbidden_tokens: ["DroneAirspace_access"]
  required_params: ["flight_zone","landing_site"]
  must_disable_tools: ["tool:web"]
  multiturn: true
```

메모:
- 위 힌트는 “정답 판정”이 아니라 **주입/회귀팩 생성/검증 자동화**를 돕는 메타데이터다.
- prior_conflict(수정된 규칙/가상 지식) 컨텍스트는 오염 위험이 크므로, 승격/메모리 저장은 기본 금지로 둔다.


---

## 5) 최소 정합성 체크리스트
- ContextBlock 수가 늘어도 “항상 전부 주입”하는 경로가 남아 있지 않은가?
- `context_overinject/context_conflict`(또는 memory_*) reason_codes가 집계 가능하게 남는가?
- SieveGenPlan 산출물이 실제 회귀팩에 **distinct queries**를 늘리는가(중복 rollouts만 늘리면 효과가 약함)?


---

## 6) 운영 로그 규약(RunLog.context_select)

- (옵션) `RunLog.context_eng`(SSOT optional): access_mode/format/navigator_used/grep_tax 등 컨텍스트 전달/탐색 관측 신호를 기록한다.
  - `enabled=true`면 `version`은 운영상 사실상 MUST(권장: `context_eng_v1`).


Selective Context Injection를 “문서상의 아이디어”가 아니라 **운영 가능한 기능**으로 만들려면, 선택 과정이 반드시 로그로 남아야 한다.

권장 규약(SSOT §RunLog의 `context_select` 사용):
- 기록 대상(최소):
  - `candidate_context_ids` (L0 통과 후보)
  - `applicable_context_ids / rejected_context_ids / unknown_context_ids` (적용성 판정)
  - `injected_context_ids` (실제 프롬프트에 주입된 ContextBlock)
- `context_select.version`: "context_select_v1"  (계측 계약 버전; 회귀 비교를 위해 고정)
- 불변식(버그 탐지):
  - `injected_context_ids ⊆ candidate_context_ids`
  - 가능하면 `injected_context_ids ⊆ applicable_context_ids ∪ unknown_context_ids`
- 위반 시 처리(권장):
  - `violated_constraints += ["context_select_invariant"]`
  - `reason_codes += ["constraint_violation"]`  (taxonomy 확장 없이 재사용)
- 저장 원칙:
  - RunLog에는 **ID만**. 원문(text) 전체는 TraceBundle로만(디버그 시에만) 남긴다.
  - `context_id`는 안정 키다. 재발급/재정렬로 ID가 흔들리면 회귀/클러스터 분석이 무너진다.
- 토큰 추정치:
  - `token_est.saved`는 절대값 정확도보다, **정책 비교용 일관성**이 중요하다(동일 추정기/동일 토크나이저 계열 유지).
