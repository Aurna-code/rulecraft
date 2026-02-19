# Rulecraft LLM Binding Playbook (Consolidated Session Notes) — r17

- 버전: r17
- 작성일: 2026-01-23 (Asia/Seoul)
- 수정일: 2026-02-18 (Asia/Seoul)
- 패치:
 - TongGeometry(GTS) — LLM 가이드 트리 서치(형식-검증 도메인) 이식
 - NN-FT(2601.14453) — FlowMap Neural Field Estimator(옵션)
 - Categorical Flow Maps(2602.12233) — 범주형 정책/개입 분포를 few-step 추정기로 증류 + test-time guidance(옵션)
 - CL-bench(2602.03587) — Context Learning 회귀팩(CLPack) + 루브릭 기반 검증(Validator L2) + CLPack v1 RegressionTestSpec 템플릿 추가(옵션)
 - Reasoning Failures Survey(2602.06176) — 실패예측 2축 라벨(ReasoningType×FailureType) + ROBUSTNESS(transform) 팩 구체화
 - Phase 1 — intent/state 기반 Memory RECALL(필터→리랭크) 실행 흐름 반영
 - Phase 2 — Folding + Memory Actions(Plan→Apply→Record) 실행 흐름 반영
 - Phase 3 — PRAXIS: ReuseBuffer 조건부 전술(conditional tactics) 운용 반영
 - LongCat-Flash-Thinking-2601 이식(HeavyThinking + 노이즈/환경 스케일링)
 - hotfix09(원천) — InFi-Check FGFC(근거/오류타입/교정) 적용 지침 추가 + 참조 갱신
 - hotfix12 — Patterning(dual of interpretability) 기반 데이터 개입(증류/회귀 데이터 믹싱)
 - hotfix12p1 — Validator/Router 무(無)모델 기본값 + 에스컬레이션 지표/트리거(관측 가능성) 추가
 - hotfix14 — Selective Context Injection(적용 컨텍스트 유닛 + 합성 쿼리 레일) 추가
 - hotfix14p4 — Selective Context Injection 운영 최소 계약(MUST/SHOULD/TUNE LATER + context_select.version) 정리
 - hotfix14p5 — Offline NavigatorGraph(오프라인) + HotPathBudget 상한 + early-exit(초기 디폴트)
 - Infomechanics(2601.15028) — IG/Cost(정보이득/비용) ledger로 should_escalate/stop를 보정(옵션)
 - hotfix14p7(2601.22401) — IntentSatisfaction(meaningful correctness) + ProvenanceProbe(prior-art/출처) 신호 추가
 - hotfix14p8(base) — 운영 정합성 최소 계약(지표 의미/옵션 신호 범위/로그 불변식/튜닝 분리) 명문화
 - hotfix14p9 — Verification gap(UNKNOWN) 명문화 + Canary/rollback 프로토콜 구체화 + ContextBlock conflict 결정적 처리 규율
 - ENCOMPASS(2512.03571) — ExecutionPathSearch(EPS): branchpoint 기반 로컬 탐색(should_escalate 하위 개입) 추가
 - TKDE DataPrep Survey(2601.17058) — DataPrep(정리/통합/보강) 운영 패턴 + 회귀팩/하네스 가이드(부록 D) 추가
 - SMEL(2602.05182) — 모델 협업 출력→단일 모델 증류(오프라인)로 런타임 비용을 1모델로 고정(옵션)

> 목적: Rulecraft를 로컬 LLM 또는 API LLM 호출 경로에 “붙여” 운영할 때 필요한 최소 구조, 안전한 확장, 오픈소스 공개 기준까지 한 파일로 정리한다.


> 관련 문서(선택):
> - Augnes Local 부록(루프 규율/근거): `RC_Addendum_rev17.md`
> - Contracts/Schema SSOT(정본): `RC_Contracts_SSOT_ssot10.md`
> - Validator 제작 사양(구현 스펙): `RC_Validator_r08.md`

---

## 1) 핵심 결론 (초단기 기억용)

- Rulecraft는 **모델 내부 플러그인**이 아니라 **LLM 호출을 감싸는 컨트롤 레이어(미들웨어/오케스트레이터)** 다.
- “전반 성능 향상”은 모델 크기보다 **루프 설계(룰 선택→실행→검증→스케일링→합성→증류/회귀)**에서 나온다.
- 그래서 `RunLog/ValidationResult/cost_profile`을 오프라인으로 집계해 **FlowMap(RiskMap/OpportunityMap)**을 만들고, `RuleSelect/should_escalate/BudgetController/Distiller`의 입력 신호로 써서 **될 구간에만 계산과 룰을 집중**한다.

- 그래서 **로컬 LLM**(Ollama/llama.cpp/vLLM 등)에도, **API LLM**(OpenAI/Anthropic/Gemini 등)에도 동일한 형태로 적용 가능하다.
- 필요한 최소 세트는 **Orchestrator(오케스트레이터)** + **LLMAdapter(generate)** + **Validator** + **Logger/Trace**.
- 계산 확대(K-drafts, compose)는 상시가 아니라 **should_escalate 트리거 기반**으로만 한다.
- “룰 저장소”는 **Rulebook**으로 명명하고, 운영 관점에서 레이어/권한/승격/회귀가 핵심이다.

---

## 1.1) 실용 응용 이식안 (운영 우선순위 요약)

> “당장 구현 순서”만 남긴다. 계약/스키마(SSOT)는 `RC_Contracts_SSOT_ssot10.md`를 따른다.

- **MVP**: `Orchestrator + LLMAdapter + ValidatorAdapter + Logger(RunLog/Trace)`
 ↳ Playbook §2~§4, Addendum §3.3~§3.4
- **자동 수습 루프**: `1-pass → verify → should_escalate → (SelfReview-1pass | K_probe→K_full+compose) → verify → log`
 ↳ Playbook §2.2/§6, Addendum §5.4/§7.3
- **형식/툴콜 안정화**: `schema validate → (auto repair 1회) → downgrade/fallback`
 ↳ Playbook §10, Addendum §3.6(Assertion)/§3.3(violated_constraints)
- **비용 제어**: `bucket×impact cost_profile` 기반 `BudgetController`로 `K/compose/max_tokens/rule_top_k` 상한 제어
 ↳ Playbook §6.4~§6.5, Addendum §5.4.4
- **노이즈/툴 상호작용 견고화**: `Noise taxonomy + ToolFuzz(회귀팩) + EnvSuite(L3)`로 tool 실패/부분 성공/비결정성을 `Validator.reason_codes`로 구조화해서 hardcase 라우팅과 회귀 우선순위를 자동화
 ↳ Playbook §6/§15, ValidatorSpec §5.1~§5.2
- **FGFC 모드(세부 팩트체크)**: 도큐먼트 기반 답변에서 L2가 `ValidationResult.fgfc`(근거+오류타입+교정)을 채워 디버깅/자동 교정/반례 생성에 직접 연결
 ↳ Playbook §2.2/§3.1.1, ValidatorSpec §5.2.2, SSOT의 FGFCReport
- **HeavyThinking 모드(테스트타임 스케일링)**: low-K 병렬 브랜치(폭) + 제한된 심화(깊이) + 요약/합성으로 “K_full 전에” 값이 있는지 체크
 ↳ Playbook §6.2.1, Addendum §5.4.2.2
- **룰 누적(자기개선)**: 로그가 쌓인 뒤 `Distiller → Consolidator → Rulebook 승격(temporary→active) → Regression`
 ↳ Playbook §15, Addendum §6
- **PASS 정의(정합성)**: `PASS iff (verdict == PASS) AND (outcome != FAIL)`
 ↳ Addendum §5.1 (이 Playbook도 동일 정의를 따른다)



## 1.2) 통합 순서(재검토 반영, 구현 체크포인트)

> Rulecraft는 “기능 추가”보다 **루프가 안정적으로 도는 순서**가 더 중요하다.
> 아래 순서를 뒤집으면, 대부분 비용 누수 또는 품질 붕괴로 끝난다.

0) **SSOT(계약) 잠금**
 - `schema_version`, id 유일성, PASS 정의(SSOT §5.1) 고정
1) **MVP 루프 고정**
 - `Orchestrator + LLMAdapter + ValidatorAdapter + Logger(RunLog/Trace)`가 항상 끝까지 돈다
2) **Validator 실체화**
 - L1(정적) 필수, 가능하면 L3(실행)로 `outcome`을 OK/FAIL로 확정
3) **should_escalate = 계산 상한 장치**
 - K-drafts/compose는 상시 금지, 트리거 기반 `probe→full` 단계형만
4) **DraftSummarizeCompose-lite(병렬-압축-합성)**
 - rollout→summary→top-m→compose(2-pass) + 재검증 + best-rollout fallback
5) **BudgetController(비용 제어)**
 - bucket×impact 비용 프로파일로 `K/compose/max_tokens/rule_top_k` 상한 제어
6) **Rulebook 승격 게이트(자기개선 통제)**
 - tests/counterexample 없는 룰은 `temporary` 유지, 자동 승격 금지
7) **FlowMap/PolicySearch(오프라인 인텔리전스)**
 - 로그가 쌓인 뒤에만 활성화. 반영은 항상 `Replay→Canary→Rollback`.

---

## 1.3) 운영 정합성 최소 계약(문서에 고정할 것만) — base(hotfix14p8)

> 여기서는 “튜닝 파라미터”를 고정하지 않는다.
> 대신 **지표의 의미/옵션 신호의 사용 범위/로그 불변식/변경관리 규율**만 고정한다.

### MUST: PASS/FAIL/UNKNOWN 의미는 SSOT를 따른다
- PASS 정의: `PASS := (verdict == "PASS") AND (outcome != "FAIL")` (SSOT §5.1)
- `outcome=="UNKNOWN"`은 “검증 불가”이지 “실패”가 아니다. 정책(should_escalate/clarify)로 처리한다.

### MUST: L2(의미/의도/선행)는 “라우팅 신호”로만 쓴다
- 기본 hot-path에서는 `v_l1_only`(L2 OFF) 유지.
- L2/L2.5는 `should_escalate` 또는 `clarify` 분기 입력일 뿐, 결과의 최종 판결이 아니다(확정은 L3).
- 숫자 임계값(EWMA/윈도우/트리거 컷)은 문서가 아니라 **프로파일(config)** 로 뺀다.

### MUST: Intent-first early-exit
- `INTENT:NOT_SATISFIED` 또는 `INTENT:PARTIAL`이면,
 - 기본은 K를 늘리는 게 아니라 **명확화/분해/산출물 슬롯 채우기**다.
 - `control_signals.exit_reason="clarify"`(또는 동급 토큰)으로 기록한다.

### MUST: Provenance는 “오염 방지 게이트”
- `PROVENANCE:LIKELY_KNOWN`이면:
 - Patterning/Distiller/Rulebook 승격 입력으로 **편입 금지(기본)**
 - 필요하면 HumanGate 또는 추가 근거로만 해제
- `PROVENANCE:CITATION_MISSING`이면:
 - “출처 요구”가 있는 태스크에서 **보강 요청**이 기본(추가 탐침은 probe/full에서만)
- `PROVENANCE:NOT_CHECKED`는 hot-path에서 정상이나, novelty 주장/리스크가 높으면 probe로 승격한다.

### MUST: 로그 불변식(운영/회귀/FlowMap을 위한 최소 기록)
BudgetController/should_escalate/early-exit가 개입한 런은 아래를 **반드시 RunLog.control_signals에 기록**하는 것을 권장한다(SSOT의 필드 활용).

- `budget_tier` (hot/probe/full)
- `budget_caps` (적용된 상한; 비교/회귀용)
- `early_exit`, `exit_stage`, `exit_reason`
- Validator의 핵심 출력(`verdict/outcome/violated_constraints`)은 RunLog에 조인 가능해야 한다(run_id 기준)

## 2) 아키텍처: Orchestrator + Adapters

### 2.1 Control Plane vs Data Plane

- **Control Plane (Rulecraft 영역)**
 룰 선택/주입, 검증, 스케일링 판단, 로그/회귀/룰 적재를 담당.
- **Data Plane (LLM 백엔드 영역)**
 로컬 엔진 또는 API 호출을 수행하고, 텍스트/툴콜 결과와 메타데이터를 반환.

### 2.2 표준 실행 흐름 (권장)

1. 입력 `x` 수신
2. (Phase 1) `intent_key/state_key`를 만들고 메모리를 **RECALL**(필터→리랭크)해 힌트를 확보
3. Rulecraft가 top-k 룰/메모리 힌트를 반영해 **주입 계획(injection plan)** 생성
4. LLM 1-pass 실행 → 후보 결과 `y0`
5. Validator로 검증 → `ValidationResult` (옵션: `fgfc`로 문장/claim 단위 근거+오류타입+교정 기록)
6. `should_escalate`면: 아래 중 하나(또는 조합)로 “보험 계산”을 수행
 - (A) **SelfReview-1pass**
 - (B) **K-drafts(+Top-m)** → compose(2-pass)
 - (C) **ReuseSeed(옵션)**: ReuseBuffer seed 선택(PUCT)로 롤아웃/탐색 재시드
 - (D) **SandboxProbe(옵션)**: LLM-in-Sandbox로 계산/근거/형식 처리
 - (E) **GuidedTreeSearch(옵션)**: 상태-행동 트리 서치(PUCT/beam) + Validator(L1/L3)로 가지치기, LLM은 제안자/휴리스틱 역할
 - (F) **ExecutionPathSearch(EPS, 옵션)**: ENCOMPASS 스타일 branchpoint 기반 실행경로 탐색(로컬 resample/beam/백트래킹)으로, K-drafts/SelfReview/GTS를 “서치 백엔드” 관점에서 통일해 운용/로깅

7. 최종 결과 출력
8. (Phase 2) **Folding + Memory Actions**: WorkingSet/Trace를 접고, `MemoryActionPlan`을 생성한 뒤 적용(`MemoryActionRecord`)하고 RunLog에 연결
9. (Phase 3) **PRAXIS(조건부 전술)**: fold 결과를 바탕으로 `ReuseBuffer.tactic_entries`를 WRITE/MERGE/RETIRE로 갱신하고, 다음 런의 RECALL 소스에 반영
10. 로그 기록, 룰 증류/적재(옵션), 회귀 테스트 등록(옵션)

---

## 3) 최소 요구 컴포넌트

### 3.1 필수

- **Orchestrator**: 전체 오케스트레이션
- **LLMAdapter**: 로컬/API 호출을 동일 인터페이스로 래핑
- **ValidatorAdapter**: 검증기(로컬/API/규칙기반 가능)
- **Logger/Trace Store**: 실행 로그, 비용, 룰 적용 정보, verdict/outcome 기록


### 3.1.1 Validator는 “1/2/3층”으로 만든다 (권장)

- **L1 정적 검증(필수)**: 스키마/형식/제약/툴콜 규칙 검사 → `violated_constraints` 중심
- **L2 의미 검증(선택)**: 저비용 grader(로컬 LLM/간단 룰/하이브리드)로 `score/reason_codes` 산출
 - (옵션, FGFC) 도큐먼트 기반 답변이면 `ValidationResult.fgfc`를 채워 **문장/claim 단위 verdict + 근거 + 오류타입 + 교정안**을 남긴다
- **L3 실행 검증(옵션, 강력 추천)**: Sandbox/하네스에서 실행·채점 → `outcome`을 **OK/FAIL**로 고정(텍스트만으로 애매한 문제에 특히 강함)

- Validator의 반환 계약은 `RC_Contracts_SSOT_ssot10.md`의 `ValidationResult`를 **MUST** 따른다.
- 제작 사양(인터페이스/합성 규칙/기본 reason_codes taxonomy)은 `RC_Validator_r08.md`를 정본으로 한다.
- 약한 모델일수록 L2를 과신하지 말고, **L1+L3로 “정답을 환경에서 뽑게”** 하는 쪽이 가성비가 좋다.

#### (추가) “무(無)모델 Validator/Router” 기본값 + 에스컬레이션 규율

- Rulecraft의 기본 목표는 **Validator/Router/BudgetController를 별도 AI 모델 없이** 먼저 완성하는 것이다.
 - Validator: L1 정적 검증(필수) + 가능하면 L3 실행 검증(테스트/샌드박스)로 `outcome`을 확정
 - Router/BudgetController: RunLog/ValidationResult/cost 집계(FlowMap) 기반 **결정적 라우팅**
- L2(의미 검증)는 기본 OFF로 두고, 붙이더라도 “판결”이 아니라 **should_escalate/선별 신호**로 제한한다.
- 에스컬레이션(=L2 붙이기) 판단은 아래 관측치로 한다(Validator Spec §0.1 참고):
 - bucket별 `UNKNOWN rate` / `insufficient_evidence rate`
 - 반복 `failure_cluster_id`
 - `exec_unavailable` (L3 부재) vs “의미 검증 부재” 구분


### 3.2 선택 (강력 추천)

- **BudgetController(Policy)**: 예산/비용/impact 신호로 `should_escalate`, `K_probe/K_full`, `synth_used`, `max_tokens`, `rule_top_k`를 **상한 통제**하는 정책 레이어
 - 핵심은 "무조건 다운그레이드"가 아니라, *버킷×impact 기준으로* 단계적으로 계산을 줄이고(Full→Probe→1-pass), high impact는 최소한의 보험 계산을 남기는 것
- **Offline FlowMap Analyzer(Policy Intelligence)**: `RunLog/ValidationResult/cost_profile`를 오프라인으로 집계해 `RiskMap`/`OpportunityMap`을 산출하고, `RuleSelect/should_escalate/BudgetController/Distiller`에 “될 놈에게만 계산” 신호를 제공
 - `RiskMap`: bucket×(stage|edge)에서 `FAIL/PARTIAL/UNKNOWN`이 집중되는 지점(필요 시 reason_codes로 분해)
 - `OpportunityMap`: 개입(`SelfReview-1pass`, `K_probe`, `K_full+compose`, 룰 타입/주입모드)이 `PASS` 회복/품질 상승을 만든 효율(`gain/cost`) 추정
- **ExecutionValidator(ValidatorAdapter, 옵션)**: “텍스트로만” 검증이 어려운 태스크(코드/실험/툴체인)에서 **실행 결과(성공/실패/메트릭)**로 `ValidationResult`를 만든다.
- **SandboxAdapter(LLM-in-Sandbox, 강력 추천)**: 일반 목적 Docker/Ubuntu 샌드박스를 data plane로 제공해, 모델이 터미널/파일을 통해 “비코드” 문제까지 해결하도록 한다.
 - 최소 툴셋: `execute_bash`(명령 실행), `str_replace_editor`(파일 생성/편집), `submit`(종료)
 - 기대 효과: (1) **약한 모델 증폭**(정확 계산/형식 강제/장문 컨텍스트 처리), (2) **관측 가능성**(행동 로그로 실패 유형 분해), (3) **루프 효율**(K를 늘리기 전에 환경으로 해결)
 - 운영 규율: `SandboxPolicy`로 네트워크/자원/턴을 캡하고, `RunLog.sandbox` + `SandboxActionTrace`로 감사/회귀 가능하게 남긴다(Addendum §3.10, ADR-0019).
 - 권장: `K_probe(저비용)` → frontier만 `K_full(+compose)`로 승격(§6.3의 Probe→Full 규칙을 그대로 재사용)
 - 운영 포인트: 평가 하네스/채점 코드는 **불변(core)** 로 두고, 패치 적용 범위를 대상 코드로만 제한(리워드 해킹 방지)
- **PolicySearchLoop(Evolutionary, 옵션)**: 실행 점수 기반으로 룰/정책 패치(트리거/예산/주입/증류 프롬프트)를 **진화적 탐색**으로 개선한다.
 - (권장) 목적함수는 평균이 아니라 *최대 개선*을 노리는 entropic utility(soft-max)를 사용하고, β는 KL-anchored로 캡해서 분포 붕괴를 방지한다(SSOT Addendum ADR-0017).
 - diversity/novelty quota를 보상에 얇게 섞어 mode collapse를 방지(§11.1/SSOT의 optional 필드 참고)
- **SummaryBuilder**: 롤아웃 결과를 `RolloutSummary`로 압축
- **Composer Pass**: 요약 묶음 기반 2nd-pass 통합
- **Distiller + Rulebook + RegressionRunner**: 룰 자동 생성/정리/회귀 운영

---

## 4) LLMAdapter 인터페이스 스펙 (권장)

### 4.1 공통 시그니처

```python
class LLMAdapter:
 def generate(self,
 messages: list[dict], # [{"role": "system"|"user"|"assistant"|"tool", "content": "..."}]
 *,
 temperature: float = 0.2,
 max_tokens: int | None = None,
 tools: list[dict] | None = None, # 툴콜/함수콜 지원 시
 response_format: dict | None = None, # 구조화 출력 지원 시
 seed: int | None = None,) -> tuple[str | dict, dict]:
 """returns (text_or_toolcall, meta)"""
```

### 4.2 메타데이터(meta) 최소 필드

- `model`: str (모델명/버전)
- `backend`: `"local" | "api"`
- `latency_ms`: int
- `tokens_in`: int (가능하면)
- `tokens_out`: int (가능하면)
- `cost_usd`: float | None (API면 실제, 로컬이면 None 또는 0)
- `rate_limited`: bool (API면 유용)
- `error`: str | None

> 토큰 수를 못 얻는 로컬 런타임도 있으니, 그땐 `latency_ms`를 우선 기록하고 필요하면 추정치를 별도 필드로 남긴다.


(권장 확장) 재현성/프로바이더 제약 관측(회귀/원인분해용):
- `temperature_req`: float | None
- `temperature_eff`: float | None (provider가 강제한 실제값)
- `seed_req`: int | None
- `seed_eff`: int | None
- `provider_constraints`: [str] | None (예: "no_temperature_control", "min_temperature_1")


---

## 5) 룰 주입(injection) 방식

- **system_guard**: GuardrailRule을 system 최상단에 배치 (우선순위 1)
- **prepend**: StrategyRule을 user 앞부분에 체크리스트/절차 형태로 추가
- **inline**: 특정 단계(도구 호출 전/출력 포맷 직전 등)에 짧게 삽입

### 5.1 적용 우선순위 (권장)

1) GuardrailRule → 2) StrategyRule → 3) 기타 힌트/예시

---


### 5.2 Context Engineering 운영 규칙 (arXiv:2602.05447) — ModelTier-aware delivery + GrepTax 관측

목표: 같은 Rulecraft라도 **모델/런타임에 따라 최적의 컨텍스트 전달 방식이 뒤집힐 수 있음**을 운영 규칙으로 고정한다.
(특히 tool-use/file-navigation이 약한 로컬/오픈소스 모델은 file-native에서 손해가 날 수 있다.)

#### 5.2.1 access_mode(컨텍스트 전달 모드)
- `file_native`(권장: frontier / tool-use 강함)
 - 필요한 조각만 파일/리소스에서 찾아 읽고(검색/읽기), 프롬프트에는 최소한만 싣는다.
- `prompt_embed`(권장: open_source / tool-use 약함 / 파일 접근 불가)
 - 핵심 룰/요약 CU를 프롬프트에 직접 주입한다(안정성 우선).
- `hybrid`
 - `prompt_embed`로 최소 “등대(lighthouse)”를 깔고, 추가 세부는 file_native로 보강한다.

권장 기본 매핑(운영 정책):
- `model_profile.tier in {"frontier","frontier_lab"}` → 기본 `file_native`
- `model_profile.tier == "open_source"` → 기본 `prompt_embed`
- 강제 다운시프트(언제든): `file_access 불가` / `tool 오류율↑` / `latency budget 작음` / `grep_tax 폭증` → `prompt_embed`로 전환

#### 5.2.2 format(구조화 컨텍스트 포맷)
- 기본: `yaml` (토큰 효율 + grep 패턴 예측 가능)
- `md`는 인간 가독성 목적이면 OK. 다만 표/구분자 많은 문서는 retrieval verbosity로 토큰이 크게 늘 수 있다.
- `custom/toon`류 “압축 포맷”은 기본 금지.
 - 허용 조건(둘 다 충족):
 1) `Navigator`에 `grep_hints`(앵커/정규식/키 패턴) 명시
 2) 회귀팩에서 `grep_tax`가 안정적임을 확인

#### 5.2.3 Navigator(인덱스/디스앰비규에이션) 우선 원칙
- 다중 파일/도메인 파티셔닝을 쓰면 `Navigator`를 1급 시민으로 둔다.
- 애매한 용어/동의어/우선순위/참조 순서는 **포맷 최적화로 해결하지 말고** Navigator에 고정한다.
- Runtime 흐름(권장):
 1) Navigator로 “어디를 볼지” 좁힘
 2) ContextBlock 선택(`context_select`)로 “무엇을 넣을지” 좁힘
 3) 최종 주입/실행

#### 5.2.3.1 Offline NavigatorGraph(오프라인) — KG로 NavigatorUnit을 자동 보강(옵션)

NavigatorUnit은 기본적으로 “사람이 쓰는 얇은 인덱스”다. 다만 문서/룰/팩이 커지면 유지비가 급격히 늘어난다.
그래서 **런타임에 KG(지식그래프)를 붙이지 말고**, 오프라인 분석기로 NavigatorUnit을 보강하는 모드를 둔다.

- 입력(권장):
 - 설계 문서/룰팩(헤더/앵커/섹션명)
 - `ContextBlock.tags/applicability_hints/pointers`
 - `RunLog.context_eng.grep_tax`(검색 시도/실패/오버헤드)
 - `RunLog.validator.reason_codes`(실패 클러스터)
- 처리(예시):
 - 텍스트 → (entity, relation, entity) 트리플 추출 → 그래프 구축
 - 공출현/중심성/커뮤니티로 “연관 섹션/룰/팩” 후보를 뽑아 `pointers/grep_hints` 제안
- 출력(권장):
 - `NavigatorUnit` 패치(새 entry 추가/기존 entry 개선)
 - “검색 실패가 많은 키워드” 리포트(=NavigatorUnit을 강화할 우선순위)
- 운용 규율:
 - 오프라인에서만 실행한다(런타임에는 **정적 NavigatorUnit만 로드**).
 - 자동 패치는 PR(리뷰) 단위로만 반영하고, 적용은 `replay → canary → rollback` 규율을 따른다.

참고 구현 시작점으로 `rahulnyk/knowledge_graph` 같은 간단한 KG 생성/시각화 템플릿을 활용할 수 있다(“데모/프로토타입” 수준으로 보고, 결과물은 항상 사람이 검수한다).

#### 5.2.4 관측(Observability): RunLog.context_eng
- 아래는 “추측”이 아니라 **회귀 가능한 운영 신호**여야 한다.
- 실행마다 `RunLog.context_eng`(SSOT optional)을 기록한다:
 - `access_mode`, `format`, `navigator_used`, `domain_partition`, `grep_tax`
- `grep_tax`가 일정 임계치 이상이면:

- `context_eng.enabled == true`이면 `context_eng.version`은 **MUST(운영 규율)** 로 채운다.
 - 권장 기본값: `"context_eng_v1"`
 - 누락 시: 파서는 `"context_eng_v1"`로 간주하되, L1에서 `context_eng_invalid`로 잡아 회귀팩에 남긴다.
 - should_escalate 트리거에 연결(상위 모델/툴로 승격)하거나
 - format/anchors/navigator를 수정해서 다시 회귀로 확인한다.
#### 5.2.5 Context Learning 회귀팩(CL-bench, 2602.03587) — “컨텍스트가 정답” 레일(옵션)

CL-bench(2602.03587)의 핵심은 “긴 컨텍스트에서 찾기(retrieval)”가 아니라,
컨텍스트에 담긴 **새 지식/규칙/절차/데이터 법칙을 학습해 적용**하는 능력(=context learning)을 측정한다는 점이다.
Rulecraft 관점에서 이건 곧 **컨텍스트 전달/주입 정책**(file_native vs prompt_embed vs hybrid, ContextBlock 선택)이 실제로 “의미 있는 정답”을 만들었는지 검증하는 회귀 레일이다.

권장 운용(현실 버전):
- hot-path 기본 OFF(비용/지연). **offline regression + canary**에서 CLPack을 굴려 정책을 고친다.
- CLPack은 “외부 검색/웹”이 필요 없도록 설계한다(컨텍스트만으로 풀 수 있게). 즉, tool policy에서 `web`을 끄는 편이 정직하다.

##### CLPack 설계 원칙(벤치마크를 ‘레일’로 번역)
- **컨텍스트 내 신규 지식**: 답에 필요한 규칙/정의/절차/상수는 컨텍스트에만 둔다.
- **사전지식 충돌 케이스 포함**: 일부 컨텍스트는 “세상 상식”과 일부러 충돌하도록 만들어, 모델이 사전지식으로 덮어쓰는지 본다.
- **멀티턴 의존성**: 같은 컨텍스트 안에서 task(i)가 task(i-1)의 산출에 의존하도록 만든다(상태 유지/WorkingSet 품질 체크).
- **verification rubrics**: 태스크당 여러 개의 요건(체크리스트)을 만든다(정답/완전성/절차/예외). “맞았다/틀렸다”만으로는 어디가 깨졌는지 안 남는다.

##### Rulecraft 매핑(최소 구현)
- Validator는 `L2-ContextLearningProbe`(Validator r08 §3.2.6)를 optional로 붙인다.
 - 결과는 SSOT §5.2.4의 `CONTEXT_LEARNING:*` 키로 `violated_constraints`에 기록(집계 키 안정성)
 - 루브릭 통계는 `score_evidence.context_learning`로 기록(SSOT §ValidationResult.score_evidence)
 - (권장) 루브릭을 `FGFCReport.unitization="rubric"`으로 남겨, **누락 항목→교정→반례 생성**까지 자동 연결한다.

##### 운영에서 “무엇을 고칠지” 연결(실용 트리아지)
- `CONTEXT_LEARNING:PRIOR_KNOWLEDGE_OVERRIDE`가 많다:
 - “컨텍스트 우선” ContextBlock(가드) 주입 + 메모리/PRAXIS 오염 방지(해당 런 산출물은 Rulebook/Memory 승격 금지)
- `CONTEXT_LEARNING:NOT_LEARNED`가 많다:
 - grep_tax/툴 안정성 확인 → `prompt_embed/hybrid`로 전환(등대 ContextBlock) + Navigator/앵커 강화
- `CONTEXT_LEARNING:INCOMPLETE`가 많다:
 - SelfReview-1pass(§6.2)나 짧은 checklist 주입으로 “누락 슬롯”을 먼저 채우고, K 확장은 나중에
- `CONTEXT_LEARNING:TURN_DEPENDENCY_BROKEN`가 많다:
 - 모델 문제로 단정하지 말고 Orchestrator/WorkingSet/Folding 버그를 먼저 의심한다(이전 turn 결과 ref가 끊기면 100% 재현된다)

주의(오염 방지):
- CLPack 컨텍스트는 종종 fictional/modified knowledge(오염 방지용)다.
 - 따라서 이런 컨텍스트에서 학습된 규칙/사실을 **전역 Rulebook/Memory로 승격**하면 바로 자기오염이 된다.
 - 기본 정책은 “run-local WorkingSet에만 두고, 승격은 금지(또는 HumanGate)”로 둔다.



## 6) should_escalate 트리거와 비용 정책

### 6.1 should_escalate 트리거 예시

- high impact (금전/의료/법/대외발송/되돌리기 어려운 작업)
- Validator verdict: `PARTIAL` / `FAIL`
- Validator outcome: `UNKNOWN` / `FAIL`
- outcome: 불확실(근거 부족, 충돌, 포맷 위반, 제약 위반)
- reason_codes: “불확실/모호/상충” 계열
- hardcase 플래그 (과거 실패 빈도 높음)
- (권장) **FlowMap 기반 hardcase**: 버킷별 `RiskMap` 상위(또는 특정 reason_codes 상위) 구간은 hardcase로 자동 승격
- complex tool interaction (멀티 턴/연쇄 툴콜/의존성 그래프)
- tool-noise 감지: `tool_timeout|tool_failure|tool_output_invalid|partial_success` 등
- env-noise 감지: 동일 입력 재실행 시 상충/비결정성(샌드박스/테스트 플래키)
- **검증 불가/근거 수집 불가 태스크**(L3/harness 없음, 외부 사실 확인 금지/불가 등):
 - `outcome=UNKNOWN`은 실패가 아니라 *확정 불가*다(ValidatorSpec §4.2).
 - 기본은 `SelfReview-1pass 1회` 또는 `명확화/분해`로 전환하고, 무의미한 `K_full+compose` 확장은 BudgetController로 캡한다.
 - `reason_codes`에 `insufficient_evidence|exec_unavailable` 등을 남겨 FlowMap에서 hardcase로 분리 집계한다.

- (hotfix14p7) `violated_constraints`에 **INTENT/PROVENANCE 신호**가 찍힌 경우:
 - `INTENT:NOT_SATISFIED|INTENT:PARTIAL` → “틀림”이 아니라 **요청 불일치/누락**이다. 기본은 K 확장보다 **명확화/분해**로 되돌린다.
 - `PROVENANCE:*` → 선행/출처 체크 신호다. 핫패스에서는 `PROVENANCE:NOT_CHECKED`가 정상이며,
 high impact/대외발송/novelty 주장에만 probe/full에서 ProvenanceProbe를 켠다.

#### 6.1.1 Intent-first early-exit(권장)

- `INTENT:NOT_SATISFIED`는 기본적으로 “탐색을 더 한다”고 해결되지 않는다.
- 권장 기본 정책:
 1) **명확화 질문 1회**(필요한 산출물 슬롯/제약을 짧게 확인) 또는
 2) Planner가 태스크를 산출물 슬롯 기반으로 분해한 뒤 재생성
- 반복되면(FlowMap에서 intent_fail이 상위) 해당 버킷에 **초기 plan 템플릿**을 넣는 게 가성비가 좋다.

#### 6.1.2 ProvenanceProbe 티어링(권장)

- **hot tier**: 기본 OFF. `PROVENANCE:NOT_CHECKED`만 남겨도 된다.
- **probe tier**: 1~2 query + top hit 요약(비용 캡). 결과는 `score_evidence.provenance`에 남긴다.
- **full tier**: 필요 시 더 깊게(단, 과다 인용 금지). `PROVENANCE:LIKELY_KNOWN`이면 novelty 주장/새 규칙 편입은 기본 차단(오염 방지).

- `PROVENANCE:CITATION_MISSING`이면(인용/출처 요구가 있는데 누락): 대외발송/외부사실/novelty 주장 태스크에서는 **즉시 should_escalate**(probe/full로 근거 확보 또는 명확한 인용 추가).
- `PROVENANCE:NEEDS_HUMAN_REVIEW`이면: 자동 판정 불가이므로 high impact에선 **HumanGate 승격**(또는 보수적으로 FAIL/ROLLBACK).



### 6.2 SelfReview-1pass (Society-of-Thought 스타일 단일 패스 내부 토론)

SelfReview-1pass는 “멀티에이전트”가 아니라, **단일 생성 호출 안에서 역할 분화와 충돌-봉합 절차를 강제**하는 *중간 티어*다.
목표는 K를 무작정 키우기 전에, **저비용으로 오류/누락/가정 충돌을 한 번 더 걷어내는 것**이다.

- 권장 사용 지점(대표):
 - `verdict in {PARTIAL, FAIL}` 또는 `outcome == UNKNOWN`
 - `reason_codes`에 불확실/상충/근거 부족이 포함
 - high impact인데 근거가 얇아 “검증을 한 번 더” 하고 싶을 때
 - 로컬 예산(시간/동시성)이 빡세서 `K_probe`조차 부담일 때

- 권장 프로파일(예시):
 - Roles: `Solver → Challenger → Mediator → Validator`
 - `sot_max_turns`: 2~3(권장 2)
 - 출력 규격: “최종 결론(1줄) + 근거/가정(3개 이내) + 버린 대안(2개 이내) + 남은 리스크(체크리스트)”
 - 길이 가드: `max_tokens`를 K-drafts보다 더 타이트하게(수다 방지)

- 종료/승격 규칙(권장):
 - SelfReview-1pass 후 Validator가 PASS/OK면 종료(추가 K 생략)
 - SelfReview-1pass 후에도 `PARTIAL/UNKNOWN`이면 `K_probe → (frontier면) K_full+compose`로 승격
 - deadzone/불능군이면(기본 정책에 따름) K 확장 금지, 명확화/분해/상위 validator로 전환

> 용어 주의: **SSOT**(Single Source of Truth, 스키마/계약의 단일 진실원천)와 **SelfReview**(Society-of-Thought, 대화적 추론 스캐폴딩)는 약어가 비슷하지만 목적이 다르다.


### 6.2.1 Heavy Thinking (폭+깊이 확장 TTC, 권장)

LongCat-Flash-Thinking-2601이 말하는 “Heavy Thinking”은 테스트타임에서 **깊이(반복/심화) + 폭(병렬 분기)**를 같이 키워 성능을 올리는 모드다.
Rulecraft에서는 이를 “K_full 전에 한 번 더” 쓰는 **중간 티어**로 넣는 게 실용적이다.

- 기본 아이디어:
 - (폭) `N`개 병렬 브랜치(서로 다른 seed/role/관점)로 후보를 만든다
 - (깊이) 각 브랜치는 `max_turns=2` 정도의 짧은 자기교정만 허용한다(수다 금지)
 - `RolloutSummary`로 압축(긴 CoT 패싱 금지) → top-m 선별 → compose(2-pass) → 재검증
- 권장 파라미터(초기값):
 - `N=3~5`, `top_m=2`, `max_tokens_per_branch`는 SelfReview-1pass 수준으로 타이트하게
 - `forbid_cot=true` 유지(요약은 “핵심 단계/가정/리스크 체크리스트”만)
- 종료 규칙:
 - HeavyThinking 후 `PASS/OK`면 종료(추가 K 생략)
 - 여전히 `UNKNOWN/PARTIAL`이면 `K_probe → (frontier면) K_full+compose`로 승격
- 로그 규율:
 - `RunLog.run_tags += ["heavy-thinking"]`
 - `RunLog.run.mode="kroll"` + `RunLog.run.cfg.plan_style="heavy_thinking_v1"`
 - `RunLog.draft_select.rollouts_n=N`, `RunLog.draft_select.top_m=top_m`


### 6.3 Probe → Full (권장)


### 6.3.0 GuidedTreeSearch(GTS) (형식-검증 가능한 도메인에서만, 선택)

**언제 쓰나**
- 수학/기하/정리증명/퍼즐처럼, (a) 상태(state)와 (b) 적용 가능한 변환(action)을 정의할 수 있고
- L1(형식) 또는 L3(실행/프로버)로 **가지치기(pruning)가 결정적으로** 가능한 경우

**핵심 아이디어(논문: TongGeometry 스타일)**
- LLM은 “정답을 직접 말하는 존재”가 아니라, 트리 서치에서 **유망한 다음 액션을 제안**하는 정책(policy) 역할
- Validator/L3(프로버/하네스)가 각 노드에서 **성립 여부(outcome)와 실패 원인**을 확정하거나 UNKNOWN으로 남김
- 선택 정책은 Rulecraft에 이미 있는 `PUCT`(ReuseSeed 선택) 메타를 그대로 재사용해서, 노드 선택에도 적용 가능

**Rulecraft 매핑(최소 구현)**
- Node state: `WorkingSet`(현재 제약/가정/목표) + `TraceBundle.refs`(근거/도형 객체 참조)
- Action: `tool_call`(기하 프로버/심볼릭 변환) 또는 “aux construction 제안(LLM)”을 `SandboxProbe`로 검증
- Search meta: RunLog에 `experiment.kind="policy_search"` + `run.mode="tree"`로 기록(SSOT/Playbook의 관측 가능성 유지)

**주의**
- GTS는 “모든 태스크 만능”이 아니다. 검증이 안 되는 영역에서 트리를 키우면 그냥 랜덤 워크가 된다(비용만 태움).


### 6.3.0a ExecutionPathSearch(EPS) — branchpoint 기반 실행 경로 탐색(ENCOMPASS 이식, 선택)

**정의**
- EPS는 “여러 번 처음부터 다시 푸는(K-drafts)” 대신,
 Orchestrator 파이프라인 안의 **불확실 결정 지점(branchpoint)** 에서만 후보를 재샘플링/탐색하는 방식이다.
- K-drafts은 EPS의 특수 케이스(= branchpoint가 시작점 1개인 depth=1 탐색)로 볼 수 있다.

**언제 쓰나**
- (a) 파이프라인이 길고, (b) 실패 원인이 특정 단계(쿼리 생성/툴 args/포맷/주입 계획)에 몰려 있고,
 (c) L1/L3로 가지치기가 가능한 경우.
- “검증 불가능한 영역에서 트리를 키우는 것”은 금지(비용만 소모).

**핵심 규율(MUST/SHOULD)**
- MUST: EPS는 상시 실행을 금지하고 `should_escalate` + `HotPathBudget`(tier/caps) 아래에서만 실행한다.
- MUST: L1 위반(형식/제약/툴콜 스키마)은 ‘수리 1회’가 실패하면 해당 분기를 **kill**(prune)한다.
- SHOULD: L3로 outcome을 OK/FAIL로 확정 가능한 도메인에서는 L3를 leaf-eval로 사용해 pruning 효율을 올린다.
- MUST: 분기 탐색 중 발생하는 부작용(파일 write, 메모리 write, 룰 승격 입력)은 **commit된 최종 경로만** 허용한다.
 - 그 외 분기는 sandbox/임시 경로에서만 실행하거나 dry-run으로 제한한다.

**SearchProfile(권장)**
- EPS 구현은 “알고리즘+예산”을 프로파일로 고정해 문서가 아니라 config로 관리한다.
 - 예: `eps_local_resample_v1`(probe): branchpoints<=2, branching<=3, depth<=2
 - 예: `eps_beam_v1`(full): beam_width<=4, node_expanded 상한, resample_policy=protect_on_exception

**로깅(MUST)**
- EPS를 사용했다면 `RunLog.context_eng.tree_search.enabled=true`를 남긴다.
- 권장: `tree_search.kind="execution_path"`, `tree_search.profile_id`, `tree_search.resampled_n/killed_n`,
 `tree_search.best_node_ref(or best_node_id)`를 채워 “왜 이 경로를 골랐는지”를 재구성 가능하게 한다.
- budget 초과/중단 시: `RunLog.control_signals.early_exit=true`, `exit_reason="budget_cap"`(또는 동급 키) 기록.

**branchpoint 추천 위치(실무 베스트)**
- `router:context_select` (주입 계획이 흔들릴 때)
- `planner:query_gen` (리트리벌/파일 탐색 쿼리가 흔들릴 때)
- `tool:args` (툴 호출 args가 자주 깨질 때)
- `format:render/parse` (JSON/YAML 깨짐, repair가 잦을 때)
- `compose:top_m_select` (top-m 선택이 품질을 좌우할 때; diversity 포함)

**ENCOMPASS 매핑(요약)**
- branchpoint → Orchestrator 단계 체크포인트(bp_id)
- record_score → ValidationResult.score + cost penalty로 만든 selection_score
- protect → 예외/파싱 실패 시 마지막 branchpoint로 되돌려 재샘플


### 6.3.1 DraftSummarizeCompose-lite 메시지 패싱 (요약→top-m→compose)

K-drafts을 “여러 개 만들기”에서 끝내면, 마지막에 모델이 그걸 무시하고 혼자 다시 풀어버리는 경우가 잦다.
그래서 **rollout 결과는 반드시 `RolloutSummary`로 압축**하고, compose(2nd-pass)는 **전체 trace가 아니라 summaries(top-m)만 입력**으로 삼는 걸 기본으로 둔다.

- 요약 산출물 계약(SSOT): SSOT `RolloutSummary`(정본) + Addendum rev11 §3.7(설명)
- top-m 선별: `ValidationResult.score + diversity` 기반(Playbook §10의 “compose가 더 망침” 케이스 대비로, compose 결과도 재검증)
- 요약 규율: `forbid_cot=true`(긴 CoT 메시지 패싱 금지) + `max_tokens` 상한



- **K_probe**(예: 3): 간단히 p_hat/p_lb95 측정
 - (초기) p_hat는 `ValidationResult.score`(예: yes_logit)를 성공확률로 취급하거나, PASS율로 추정
- **Frontier band**(예: 0.3~0.7): 가치가 있는 구간이면 **K_full**(예: 6~8) + compose
- **Deadzone**(예: p_lb95 < 0.05): K 확장 금지. 문제 분해/명확화/상위 모델 에스컬레이션

### 6.4 BudgetController(비용-성능 피드백 루프)와 예산 초과 정책

원칙: **비용을 ‘벌금’이 아니라 ‘입력 신호’로 취급**해서, 같은 안전 수준을 더 적은 계산으로 유지한다.

- `cost_profile[bucket, impact]`(권장: EWMA + p95)를 누적한다. bucket은 `task_type`/`failure_cluster`/`domain_tag` 중 하나로 시작하고, impact는 `normal/high`만으로도 충분하다.
- 예산이 빡세질수록 **단계형으로 계산을 줄인다**: `Full → Probe → 1-pass` (그리고 compose는 가장 먼저 꺼진다).
- 단, **high impact에서 ‘하드 캡 = 무조건 다운그레이드’는 금지**: 최소한 `K_probe` 수준의 보험 계산은 남기고, 대신 다른 버킷(normal)에서 먼저 감산한다.
- 하드 캡 시 우선순위(권장):
 1) compose off
 - (권장) provenance_probe off (있다면; 핫패스는 원래 OFF)
 2) `K_full` 상한 하향
 3) `K_probe` 유지(특히 high impact)
 4) `max_tokens`, `rule_top_k` 캡
 5) 도구/비싼 validator 차단 → 요구사항 명확화/분해
#### 6.4.1 HotPathBudget(상한치) + early-exit — 초기 디폴트(rc_default_light_v1)

Rulecraft를 “미들웨어”로 붙였을 때 무거워지지 않게 하려면, **기본을 hot-path로 두고** 트리거가 떠야만 계산을 키워야 한다.
아래는 “처음 붙일 때” 가장 무난한 디폴트다(환경/모델/도메인에 따라 조정).

**Budget tiers (권장 기본값)**
- `hot` (기본): *1-pass + L1 verify*로 끝낸다.
 - caps: `max_tokens_total≈1200`, `max_tool_calls=0~1`, `max_latency_ms≈2500`
- `probe` (보험): `K_probe` 또는 `SelfReview-1pass` 1회까지 허용한다.
 - caps: `max_tokens_total≈2500`, `max_tool_calls≤2`, `max_latency_ms≈6000`
- `full` (하드케이스): `K_full+compose(+재검증)`까지 허용한다.
 - caps: `max_tokens_total≈6000`, `max_tool_calls≤6`, `max_latency_ms≈15000`

**Tier 선택 규칙(권장)**
- 기본은 `hot`.
- 아래 중 하나면 `probe`로 승격:
 - `impact=high` 또는 `verdict∈{PARTIAL,FAIL}` 또는 `outcome∈{UNKNOWN,FAIL}` 또는 hardcase 플래그
- `probe` 후에도 frontier(불확실/불일치/근거 빈약)면 `full`로 승격.
- deadzone(개선 불능군)면 `full` 금지: 문제 분해/명확화/상위 모델/샌드박스로 전환.

**Early-exit 규칙(권장)**
- 어떤 티어든, 아래면 즉시 종료(=추가 계산 생략):
 - `Validator PASS`이고 `outcome==OK` (또는 도메인상 더 볼 게 없음)
 - `probe`에서 `p_lb95`가 충분히 높음(예: ≥0.8) → `full+compose` 생략
- 반대로 아래면 “계산 확대” 대신 종료/전환:
 - `deadzone`(예: p_lb95 매우 낮음) → K 확장 금지, 명확화/분해
 - tool/harness 불가로 `outcome=UNKNOWN`이 반복 → `SelfReview-1pass` 1회 후에도 해결 안 되면 요구사항 명확화

**로그 규율(권장)**
- 선택된 티어/상한/early-exit 사유를 `RunLog.control_signals.budget_* / exit_*`에 남긴다(SSOT hotfix14p5).

- (선택) **오버드래프트/부채 모델**: high impact에서 cap을 잠깐 넘겼으면, 이후 N분/다음 M요청에서 동일 bucket의 K/compose를 자동 감산해 ‘상환’한다(로그로 남김).


### 6.5 FlowMap(RiskMap/OpportunityMap) 기반 트리거 보정(권장)

- 목적: 불확실하다는 이유로 계산(K/compose)을 **무작정 늘리지 말고**, 오프라인 지도에서 “돈값하는 개입”만 선택한다.
- 입력: `RunLog`(run.mode/applied_rules), `ValidationResult`(verdict/outcome/reason_codes), `cost_profile[bucket×impact]`
- 출력:
 - `RiskMap`: 실패/불확실이 집중되는 stage/edge
 - `OpportunityMap`: 개입별 `PASS` 회복(또는 품질 상승) `gain`과 `cost`를 합친 `efficiency=gain/cost`

**추가(옵션): 학습된 FlowMap 추정기**
- 버킷이 희소하거나 노이즈가 큰 경우, 집계표 대신/보조로 `nn_field_v1` 같은 작은 NN을 붙여 `risk/opportunity`를 추정할 수 있다(Addendum §3.8.1, SSOT `FlowMapSnapshot.estimator`).
- 출력이 범주형(예: `intervention`, `budget_tier`, `top_reason_code`) 중심이면, `cat_flow_map_v1` 같은 Categorical Flow Maps(2602.12233) 계열로 “few-step policy sampler”를 만들 수 있다(Addendum §3.8.1.1).
 - 장점: self-distillation로 1~few-step 추론 + 테스트타임 reweighting(guidance)로 “현재 목표(IG/Cost, 예산, impact)”에 맞춰 분포를 기울일 수 있다.
 - 주의: 어디까지나 **policy hint**. baseline과 replay/canary 없이는 붙이지 말 것.
- 단, 위 어떤 경우든 “정책 힌트”일 뿐 판결이 아니다. 반영 규율은 동일하게 `replay → canary → rollback`만 허용.

**적용 규칙(권장)**
- `OpportunityMap`이 낮은 버킷은, 트리거가 떠도 `K_full+compose`로 가지 말고 `SelfReview-1pass` 또는 요구사항 명확화/분해로 전환한다.
- `RiskMap`이 높은 버킷은 GuardrailRule을 우선 주입하고(`system_guard`), `applied_rules[].reasons`에 `risk_hotspot=...`, `opp_hotspot=...` 같은 태그를 남겨 정책 튜닝 가능성을 높인다.
- `BudgetController`는 `efficiency`를 기준으로 “full을 남길 버킷”과 “probe/1-pass로 강제할 버킷”을 단계형으로 나눈다.

---


### 6.6 Patterning(데이터 개입) — “어떤 데이터가 어떤 일반화를 만들까”를 역으로 푸는 루프(옵션)

arXiv:2601.13548 *Patterning: The Dual of Interpretability*의 핵심은,
- **관측가능한 구조 지표(Observable) 변화** `dμ` 와
- **데이터 분포 파라미터(h) 미세 변화** `dh`
사이를 **susceptibility 행렬 χ**로 선형 근사하고(`dμ = χ·dh`),
원하는 목표 변화 `dμ_target`를 만드는 **최소 개입**을 `dh = pinv(χ)·dμ_target`로 구하는 것이다.

Rulecraft에선 내부 회로를 직접 읽을 필요 없다. 대신 “구조”를 **행동 프록시(관측치)**로 두고,
`h`를 “로그에서 추출한 데이터 슬라이스/반례 타입/생성기 템플릿의 가중치”로 둔다.

#### 적용 대상(현실적인 것만)
- Distiller가 만드는 `distill_dataset` 샘플링 비율(예: reason_code별 반례 비중)
- CounterexampleGenerator / Composer 프롬프트 템플릿 혼합 비율
- (선택) LoRA/SFT용 샘플 가중치(로컬에서만, canary 필수)

#### 최소 구현(권장)
1) **Observables μ**(측정값):
 - `pass_rate[bucket]`, `unknown_rate[bucket]`
 - `reason_code_rate[bucket, code]` (예: format_leak/tool_misroute/...)
 - `avg_cost[bucket]` (제약: 비용 폭발 방지)

2) **Probes h**(개입 레버):
 - 데이터 슬라이스 K개(예: “format_leak 반례”, “tool_misroute 반례”, “실행 성공 트레이스”, “요구사항 불명확 케이스”)

3) **χ 추정(가성비 버전)**:
 - 각 probe k의 샘플링 가중치를 `+ε` 만큼 올린 “미세 개입”을 만들고,
 - 동일 canary/replay 세트에서 μ 변화를 측정해 `χ_{i,k} ≈ Δμ_i / ε` 로 근사한다.
 - `ε`는 작은 값(예: 0.05) + 클리핑으로 안정화한다.

4) **개입 해(가중치 계산)**:
 - 목표 `dμ_target`(예: 특정 reason_code_rate를 낮추고 pass_rate를 올림)을 만들고
 - `dh = pinv(χ)·dμ_target`를 계산한다(릿지 정규화 권장).
 - `dh`는 `[0, w_max]`로 클립하고 총합을 1로 재정규화한다.

5) **적용/검증**:
 - 결과는 `PatterningPlan`으로 기록한다(SSOT optional extension 참조).
 - 적용은 항상 `replay → canary → rollback` 규범을 따른다. 회귀(regress)면 즉시 롤백.

#### 6.6.1 Selective Context Injection(적용 컨텍스트 유닛 + 합성 쿼리) — Patterning/회귀팩 강화(옵션)

SIEVE의 핵심은 “컨텍스트를 통째로 주입하면 노이즈가 늘고, 질의별로 **적용되는 조각만** 주입해야 학습/회귀 신호가 깨끗해진다”는 관찰이다.
Rulecraft에서는 이를 **(A) 런타임 선택적 주입** + **(B) 오프라인 합성 회귀팩**으로만 도입한다.

(A) 런타임: ContextBlock 기반 선택적 주입
- Rulebook/Policy/PRAXIS 전술/메모리 힌트를 `ContextBlock`로 원자화한다(SSOT optional extension 참조).
- Router는 질의 q에 대해 L0(cheap) 필터(tags/키워드/슬롯)로 ContextBlock 후보를 top-N으로 줄이고,
 필요하면 Validator L2-Applicability로 적용성만 확인한다(“판결”이 아니라 should_escalate 트리거 관점).
- ContextBlock 과다/상충 시 `reason_codes`에 `context_overinject/context_conflict`(옵션) 또는 `memory_overinject/memory_conflict`를 남겨 FlowMap/회귀에 사용한다.

(A') 관측/운영 정합성(필수에 가까움: 돌려보고 튜닝하려면 먼저 기록해야 함)
- **MUST**: `RunLog.context_select`를 남긴다(SSOT §RunLog). RunLog에는 **ID만** 기록한다.
 - 최소: `policy / candidate_context_ids / injected_context_ids`
 - 권장: `applicable_context_ids / rejected_context_ids / unknown_context_ids / conflict_pruned_context_ids / token_est.saved`
 - `context_select.version`: "context_select_v1" (계측 계약 버전; 회귀 비교를 위해 고정)
- **MUST**: 불변식 위반은 실행/로그 버그로 취급한다.
 - `injected_context_ids ⊆ candidate_context_ids`
 - 가능하면 `injected_context_ids ⊆ applicable_context_ids ∪ unknown_context_ids`
 - 위반 시: `violated_constraints += ["context_select_invariant"]` + `reason_codes += ["constraint_violation"]`
- **SHOULD**: 오프라인 집계 지표의 *정의*만 고정한다(임계값은 나중에).
 - `context_unknown_rate`, `context_token_saved_mean`, `reason_code_rate(context_conflict|applicability_unknown|memory_conflict 등)`
- **TUNE LATER**: canary gate 임계값/정책(얼마면 실패로 볼지)은 replay/canary 실측 후 고정한다.


(B) 오프라인: SieveGenPlan로 합성 쿼리/데이터 생성
- 입력(seed): 실패 클러스터 대표 q + ContextBlock seed 조합(c_seed)
- 생성: c_seed가 “적용되는” 합성 질의 q'를 만든다.
- 검증: q'에 대해 적용 CU만 남겨 `(q', applicable_context_ids)` 형태의 `SieveExample`을 기록한다.
- 사용: Distiller의 distill_dataset/CounterexampleGenerator 템플릿 믹싱 probe로 투입한다.
- 배포 규율: 생성/가중치 변경은 항상 `replay → canary → rollback`로만 반영한다(온라인 즉시 반응 금지).

#### 금지 사항
- 런타임에서 즉시 반응하는 “온라인 패턴링”은 금지. 학습-평가-배포 경계를 깨면 사고 난다.

---



### 6.7 Infomechanics(2601.15028) — 정보이득/비용(IG/Cost) 기반 should_escalate 보정(옵션)

**목표**: “그냥 더 생각해”가 아니라, *추가 계산이 불확실을 얼마나 줄일지*를 로그 기반으로 판단한다.

운영 루프(권장):
1) Orchestrator가 후보를 만들고(L0/L1), Validator가 신호를 만든다(L1/L2/L3).
2) `p_pass` 추정치를 갱신하고, `info_gain_bits`와 `ig_per_cost`를 계산한다.
3) 아래 트리거를 만족하면 확장(rollout↑, tool↑, GTS/DraftSummarizeCompose-lite)하고, 아니면 멈춘다.

권장 트리거(예시, 정책으로 고정):
- **scale** if `(ig_per_cost >= τ_ig)` OR `(mode_count_eff >= τ_mode AND ig_per_cost is not collapsing)`
- **stop/commit** if `ig_per_cost`가 연속 K번 감소하거나, 절대값이 `τ_stop` 아래로 떨어짐
- **debug** if `info_gain_bits`가 음수로 누적(=불확실 증가): 주입/제약 상충(`instruction_conflict`, `memory_conflict`)을 먼저 해결

실제 계산(프록시):
- `p_pass`는 bucket의 경험값 + L1/L3 강한 증거 + L2 약한 보정으로 갱신(Validator spec r08의 hook 참고).
- `mode_count_eff`는 rollouts/top-m 클러스터링 기반(요약 임베딩)으로 산출한다.

주의:
- 숫자는 “최종 진실”이 아니라 **정책 비교/회귀**를 위한 계측치다.
- cost 단위를 토큰/지연/요금 중 하나로 고정해야 `ig_per_cost`가 의미를 갖는다.


### 6.8 SMEL(2602.05182) — 모델 협업을 “한 모델”로 증류해서 핫패스 비용을 깎기(옵션, 오프라인)

핵심 아이디어: 런타임에 여러 모델/여러 패스(토론/비평/합성)를 상시로 돌리는 대신, 
오프라인에서 “협업 시스템(teacher)”이 만든 좋은 출력을 데이터로 모아 **단일 모델(student)** 을 SFT/LoRA로 키운다. 
그리고 평상시(핫패스)는 student 1번 호출로 끝낸다.

Rulecraft에선 이게 특히 자연스럽다. 이미 `K-drafts + compose`(협업의 한 형태)와 `Validator/회귀팩`(품질 게이트)이 있기 때문이다.

#### 권장 운영 절차(현실 버전)
1) **Teacher(협업) 정의**
 - (가벼움) 같은 모델로 `K-drafts → compose`
 - (강함) 서로 다른 모델/티어로 역할 분리: `solver / critic / synthesizer`
 - (선택) 질의별 **router**로 “이 질문엔 이 모델” 선택(API-level collaboration)

2) **데이터 수집**
 - 버킷/도메인별 대표 입력 X를 잡고 teacher로 실행
 - 로그는 `RunLog.experiment.kind="collab_distill"`로 찍어 두면 나중에 회귀/분석이 편하다(SSOT optional extension)

3) **필터(오염 방지)**
 - 기본: `PASS && outcome=="OK"`만 증류 데이터로 채택
 - `PASS && outcome=="UNKNOWN"`은 “검증 불가” 타입만 제한적으로(환각 위험 있는 UNKNOWN은 제외)

4) **증류(학습)**
 - 기본: supervised KD = teacher 출력으로 SFT/LoRA
 - 초기(teacher–student gap 큼): **multi-student KD**(teacher : best_student : self = α:β:γ) 권장 
 ↳ Rulecraft에선 3슬라이스를 `PatterningPlan.probes`로 두고 weight를 찾는 방식이 가장 덜 위험하다.

5) **평가/배포**
 - 모델/어댑터 교체는 룰 변경과 동일 취급: `replay → canary → rollback`
 - Micro-Regression 팩(특히 format/tool-policy)은 “필수”로 고정

6) **런타임 정책**
 - default는 student (1회 호출)
 - 실패/불확실 트리거(should_escalate)에서만 teacher급(고티어 호출, 또는 K-drafts/compose)로 에스컬레이션

#### 주의(현장 사고 포인트)
- student가 좋아져도 **Validator는 빼지 않는다**: “실수는 비용보다 비싸다.”
- teacher 로그에 **민감정보가 섞이지 않게** 익명화/필터 규칙을 고정한다(패턴링과 동일).
- 무한 반복(evolution)은 금지. 반복 횟수는 회귀팩으로 제동 걸어야 한다(좋아졌다는 착시 방지).

---

## 7) Rulebook: 레이어/권한/수명(TTL)

Rulebook은 단순 저장소가 아니라 **운영 제어 장치**다. 공개/협업을 생각하면 레이어와 권한 분리가 필수.

### 7.1 권장 레이어

- `Rulebook.Core` (불변): 시스템 안전/보안/권한 모델의 뼈대. 최상위 우선순위.
- `Rulebook.Project`: 프로젝트 운영 규칙(팀/리포 기본값).
- `Rulebook.UserOverlay`: 권한 없는 유저 경로. 기본은 좁은 scope + TTL.
- `Rulebook.TrustedOverlay`: 권한 있는 유저 경로. 품질 저하는 본인 책임(단, 보안/권한은 별도).
- `Rulebook.SessionOverlay`: 세션 한정(강한 TTL), 실험용.

### 7.2 우선순위 (권장)

`Core Guardrail > Project Guardrail > User Guardrail(add-only) > Strategy(Project→User)`

> 핵심: 유저가 룰을 넣을 수는 있어도 Core/Project를 “무력화”는 못 한다.



### 7.3 검색/리콜(Phase 1, 권장)

Rulebook/ReasoningBank/ReuseBuffer는 “그냥 벡터 검색”으로 붙이면 재사용률이 급격히 떨어진다.
Phase 1의 목표는 **intent/state 호환성으로 먼저 걸러서** “틀린 힌트”를 줄이는 것.

- **intent_key (안정)**: domain/task/tools/output/constraint 기반. “이런 종류의 작업”인지 판단.
- **state_key (휘발)**: run.mode/budget/policy/tool/sandbox/validator 프로필 기반. “지금 실행 가능한가” 판단.

권장 파이프라인(SSOT §4.4):
1) Candidate gather(소스별 top-k’): Rulebook, ReasoningBank, ReuseBuffer(tactic_entries)(Phase 3), 필요 시 최근 TraceBundle
 - seed/prior 재시드는 RECALL이 아니라 `reuse_select`(PUCT) 경로로 분리
2) Filter: bucket/intent/state 불일치 컷 + retired/저품질 컷
3) Rerank: `semantic + intent + state + quality` 가중합
4) top-m을 짧은 **MemoryHint**로 주입(장문 금지, refs 우선)

**메모리 주입 예산(권장 기본값)**
(가볍게 굴리려면 숫자로 때려 박아야 한다.)

- `MemoryHint.summary`: ≤ 120 tokens (또는 ≤ 600 chars)
- `ConditionalTactic.injection.content`: ≤ 160 tokens (또는 ≤ 800 chars)
- 한 run에서 (룰 제외) 메모리 주입 총합 ≤ 256 tokens
- 상한 초과 시: 더 압축하거나 `payload_ref`로 넘기고, Orchestrator는 초과분을 잘라서 주입

관측 가능성:
- 실제 사용한 memory/rule id는 RunLog의 `memory_recall.used_ids`에 남겨라. 아니면 “왜 좋아졌는지/나빠졌는지” 추적이 안 된다.

---


### 7.4 Folding + Memory Actions (Phase 2, 권장)

Phase 2는 “리콜(Phase 1)로 가져온 것을 기록”하는 수준을 넘어,
런이 끝날 때(또는 트리거 발생 시) **재사용 가능한 단위로 접고(Folding)**,
필요한 메모리 오퍼레이션을 **자동으로 계획/적용**한다.

권장 트리거:
- `end_of_run` (기본)
- `ws_overflow`
- `fail_cluster` (반복 실패/제약 위반 패턴)
- `phase_shift` (probe→full 등)

권장 절차(Plan→Apply→Record):
1) `fold()` → `FoldResult` 생성(WorkingSet/Trace/ValidationResult 기반)
2) `plan_memory_actions()` → `MemoryActionPlan` 생성
3) `apply_memory_actions()` → `MemoryActionRecord[]` 생성
4) RunLog에 `memory_fold` / `memory_actions`로 연결(관측 가능성)

안전장치:
- Rulebook은 “승격 룰 저장소”다. Phase 2 자동화는 `active` 승격을 하지 않는다(temporary/draft만).
- PRUNE는 PIN/보존 대상 제외. 기본은 RETIRE 우선.


### 7.5 PRAXIS: 조건부 전술(conditional tactics) 운용 (Phase 3, 권장)

목표: “재사용 가능한 전술”을 Rulebook(강한 규칙)로 바로 올리지 말고, **조건부 힌트 저장소**(ReuseBuffer.tactic_entries)에 먼저 쌓아 가성비를 본다.

- 단위: `ConditionalTacticRecord`
- 리콜: `RECALL(intent,state)`의 소스에 `ReuseBuffer`(tactic_entries)를 추가한다.
- 주입: 길이 제한(짧게), 충돌 시 **가장 보수적인 전술만** 남기고 나머지는 무시(또는 RETIRE 후보로 기록).
- 갱신: Phase 2의 Folding/Memory Actions가 끝난 뒤, 아래 3가지 중 하나로 반영한다.
 - WRITE: 새 전술 기록(처음 등장)
 - MERGE: 중복/유사 전술을 합쳐 상위 요약으로 정리
 - RETIRE: 실패/부적합/노이즈 전술 비활성화(기본), PRUNE는 제한적으로

관측 가능성:
- 사용된 전술은 RunLog의 `praxis.used_tactic_ids`에 남긴다.
- 실패 시(Validator FAIL/정합성 깨짐) `praxis.retire_candidate`를 만들고, 다음 compaction에서 RETIRE한다.

---

## 8) 유저 룰 입력(User Rule Submission) 설계

“유저가 직접 룰을 집어넣는” 기능은 제품성이 강하지만, 자유 텍스트 무제한 허용은 사고 루트다. 최소 구조를 강제한다.

### 8.1 기본 원칙(안전장치)

- 기본값은 `temporary` + TTL + 좁은 scope(태스크/태그/툴/출력).
- 유저는 **추가(add)** 는 가능, **제거/완화(remove/disable)** 는 불가.
- 권한 없는 유저는 `system_guard` 금지. `prepend/inline`만 허용.
- 적용 전 **Rule Lint + Conflict Check + Dry-run**.
- 승격(promote)은 테스트 없으면 금지. 좋은 룰은 “candidate”로만 올리고 조건 충족 시 승격.

### 8.2 최소 스키마(권장)

```yaml
RuleSubmission:
 schema_version: "0.1.0"
 submission_id: string # MUST (로그/감사를 위한 안정 ID)
 created_at: string|null # MAY (ISO8601)
 title: string
 type: "strategy" | "guardrail"
 scope:
 tags: [string] # 예: ["writing", "code", "finance"]
 tools: [string] # 예: ["web", "filesystem"]
 outputs: [string] # 예: ["json", "markdown"]
 injection_mode: "prepend" | "inline" # (권한 없는 유저는 system_guard 금지)
 priority: int # user 범위 내에서만 의미
 ttl: "session" | "hours:6" | "days:1"
 text: string
 rationale: string? # optional
```

### 8.3 Lint에서 즉시 거르는 금지 패턴(예시)

- “앞의 지시를 무시” / “규칙을 공개” / “로그를 출력” / “키/비밀을 출력” 류
- tool-call을 무조건 실행(권한 상승)
- Validator 결과 무시/우회 지시

---

## 9) Trusted vs Untrusted 정책 (공개 프로젝트 기본)

오픈소스 공개를 전제로 하면, 기본은 Untrusted가 맞다. Trusted는 명시적 opt-in.

### 9.1 역할(Role) 예시

- `admin / trusted / user / guest`

### 9.2 정책(요약)

- **Trusted path**: 룰 추가/수정/삭제/전역 적용 허용(품질 저하 본인 책임)
- **Untrusted path**: 룰은 제안/세션 TTL/좁은 scope만 허용, `system_guard` 금지, Core/Project 무력화 금지

### 9.3 Trusted라도 남겨야 하는 최소 가드(권장)

- 다른 사용자 데이터 접근 금지(멀티유저/공유 환경이면 필수)
- 키/로그 유출 방지(본인만 아픈 문제가 아님)
- tool 권한 모델은 룰로 바꿀 수 없게 고정(권한 상승 루트 차단)

---

## 10) 실패 모드 Runbook (운영자용)

| 실패/징후 | 대표 원인 | 1차 조치 | 2차 조치(필요 시) |
|---|---|---|---|
| Validator FAIL/UNKNOWN | 근거 부족, 충돌, 제약 위반 | 명확화 질문 / 제약 재주입 | K_probe→K_full / 상위 Validator / 보험(API) |
| tool-call JSON 파손 | 출력 포맷 불안정 | schema validate → 자동 repair 1회 | 텍스트 모드 강등 + 사용자 확인 |
| compose가 더 망침 | 통합 환각/과잉 일반화 | compose 결과도 재검증 | FAIL이면 best rollout로 fallback |
| rollouts 다양성 부족 | mode collapse/후보가 다 비슷함 | diversity_score 확인, resample | top-m 강제 + novelty/transform 적용 |
| API timeout/rate limit | 네트워크/쿼터 | 백오프+jitter, 재시도 제한 | circuit breaker(잠시 차단), 로컬/대체 모델 |
| 로컬 OOM/KV 폭발 | 컨텍스트/동시성 과다 | 컨텍스트 요약, max_tokens 제한 | 동시성↓, 모델 다운시프트, prompt 축소 |
| 비용 폭발(API) | should_escalate 과다/롤아웃 남발 | probe만 유지, compose off | untrusted 강화, 하이브리드 validator 전환 |

---

## 11) 관측 가능성(Observability) 표준

### 11.1 권장 로그 필드(최소)

- (SSOT/RunLog) `schema_version`, `run_id`, `input_ref`, `bucket_id`
- (SSOT/RunLog) `run_tags`, `control_signals`(risk/opp/efficiency)
- (SSOT/RunLog) `applied_rules[]`(rule_id/version/type)
- (SSOT/RunLog) `run.mode`, `run.cfg`(temperature/seed_prompt/plan_style/self_refine_steps/tool_order)
- (SSOT/RunLog) `sandbox.*`(enabled/network/turns/actions_n/traces_ref...)
- (SSOT/RunLog) `sot_profile`, `sot_max_turns`, `outputs.self_review_signals`
- (SSOT/RunLog) `outputs.*`(output_ref/draft_summary/compose_inputs...)
- (SSOT/RunLog) `validator.*`(validator_id/verdict/outcome)
- (SSOT/RunLog) `cost.*`(latency_ms/tokens_in/tokens_out/tool_calls)
- (SSOT/RunLog) `draft_select.*`(rollouts_n/top_m/selection_method/selected_summary_ids/diversity_score)
- (SSOT/RunLog) (옵션) `experiment.*`, `reuse_select.*`, `repr.*`
- (SSOT/RunLog) (옵션, Phase 1) `memory_recall.*`
- (SSOT/RunLog) (옵션, Phase 2) `memory_fold.*`, `memory_actions.*`

- (콜 레벨/별도 스토어 권장) `backend`, `model`, `adapter_version`, `cost_usd`, `rate_limited`, `error`
- (제품/서비스 레벨) `request_id`, `session_id`, `failure_class` 등은 RunLog 외부에서 함께 묶어도 된다(SSOT 강제 필드는 아님).


### 11.2 샘플링 정책(권장)

- 정상: 1~5% 저장
- 실패/UNKNOWN: 100% 저장
- high impact: 100% 저장 + 리다액션(민감정보/키/개인정보)
 - 리다액션 최소 범위(권장):
 - 사용자 입력/출력 원문에서 개인식별자/비밀키/토큰/세션 쿠키/내부 URL/query 등 “재사용 가능한 비밀” 제거 또는 마스킹
 - RunLog/TraceBundle에는 원문을 직접 담지 않고 refs로 분리(SSOT TraceBundle 코멘트 준수)
 - 보존/접근(권장):
 - 원문 스토어는 TTL/접근제어를 기본으로 하고, 운영자가 아닌 분석 파이프라인에는 최소화된 텍스트만 전달

---

## 12) 로컬 LLM 적용

### 12.1 장점
- 데이터가 로컬에만 남음(프라이버시/주권)
- 병렬 롤아웃을 과금 부담 없이 시도 가능(대신 시간/전력)
- 백엔드 커스터마이징 자유도 높음

### 12.2 제약
- VRAM/컨텍스트/속도 한계가 병목
- tool-call/구조화 출력/logprobs 지원 편차 큼
- 동시성(병렬 롤아웃)에서 런타임 안정성 차이

### 12.3 로컬 예산 정의 예시
- `budget = time_ms` 또는 `budget = joules` 또는 `budget = (time_ms, max_concurrency)`

---

## 13) API LLM 적용

### 13.1 장점
- 모델 품질/도구 기능 지원이 대체로 안정적
- 로컬 하드웨어 제약에서 탈출
- 구조화 출력/툴콜 운영이 쉬움

### 13.2 제약 및 운영 주의점
- K-drafts은 곧 비용 증가. should_escalate가 필수
- 레이트리밋/쿼터로 병렬 설계가 막힐 수 있음
- 민감 컨텍스트/룰/로그는 요약/마스킹 후 전송 권장

---

## 14) 하이브리드 권장 조합

1) **API 메인 + 로컬 validator**: 품질 확보, 검증 비용 절감
2) **로컬 메인 + API validator(보험형)**: 평소 0원, 위험 시만 API
3) **로컬 메인 + 로컬 validator**: 완전 로컬(성능은 하드웨어가 결정)
4) **API 메인 + API validator**: 가장 깔끔하지만 비용이 가장 무겁다

---

## 15) 릴리즈/버전/회귀(Regression) 운영

### 15.1 Rulebook 상태 전이(권장)

- `temporary`: 실험/세션 룰. 테스트 없어도 존재 가능(기본 TTL).
- `active`: 회귀/반례 최소 기준 통과 후 승격.
- `retired`: 성능 악화/충돌/쓸모 없음 확인 시 퇴역(롤백 가능).

### 15.2 승격 최소 기준(권장)

- **기본 최소(프로토타입)**
 - 회귀 1개 이상(스모크)
 - 반례 2개 이상(클러스터형 1 + 경계형 1 권장)

- **오픈소스/운영 모드(권장 강제)**
 - Micro-Regression(자동 채점) 5개 이상
 - 반례 2개 이상(클러스터형 1 + 경계형 1)
 - Distiller가 `failure_prediction`(작동 가설 + 의존성 + 실패예측 2개 이상)을 포함
 - 위 강화 기준을 못 채우면 `active`로 올리지 말고 `temporary`로 남긴다(코어 셋 제외).


### 15.3 Canary/롤백(권장) — 최소 실행 프로토콜

정의(운영 용어 고정):
- **replay**: 고정된 회귀팩/대표 버킷 샘플로 “오프라인 재현”을 먼저 돌려 회귀를 잡는 단계
- **canary**: 제한된 트래픽/샘플에서 “온라인 영향”을 확인하는 단계
- **rollback**: 악화 시 즉시 이전 상태로 되돌리는 단계(룰/정책/프로파일을 분리 롤백 가능해야 함)

권장 절차(최소):
1) replay(오프라인)
 - 대상: (a) Micro-Regression Pack, (b) 최근 failure_cluster 상위 K, (c) high impact 버킷 샘플
 - 통과 조건(예시): FAIL/UNKNOWN 상승 없음 + 비용/지연 급증 없음
2) canary(온라인)
 - 적용: 1~5% 트래픽 또는 샘플링 게이트(버킷/도메인별)
 - 관측: RunLog.control_signals(budget_tier/exit_reason/early_exit 등) + ValidationResult(verdict/outcome) + cost/latency
 - 롤백 트리거(예시): FAIL 상승, UNKNOWN 상승(특히 exec_unavailable 계열), cost/latency 급증, high impact 버킷 악화
3) promote 또는 rollback
 - promote: canary 통과 후 점진 확장
 - rollback: 악화 시 “전체”가 아니라 **변경 단위별**로 되돌린다
 - (a) 룰만 롤백
 - (b) BudgetController/프로파일(임계치/상한)만 롤백
 - (c) 주입 정책(ContextBlock/memory)만 롤백

규범:
- 정책/가중치 변화는 항상 replay→canary→rollback을 따른다(“로그 보고 즉시 prod 반영” 금지).
- 롤백은 “즉시 가능”해야 하므로, 변경 단위(룰/프로파일/주입 정책/코드)를 분리 배포한다.


### 15.4 실패예측(taxonomy) 운영 규율(권장)

- Distiller는 룰을 만들 때 “왜 먹히는가”만 쓰지 말고, **어떻게 깨질지**를 같이 낸다.
- *Large Language Model Reasoning Failures* (TMLR 01/2026; arXiv:2602.06176)의 관점(2축)을 **스키마 변경 없이** 운영에 얹는다:
 - `reasoning_type`: informal|formal|embodied (어떤 종류의 추론이 핵심인지)
 - `failure_type`: fundamental|limitation|robustness (근본/도메인 한정/변형 민감)

이 2축은 “분류” 자체가 목적이 아니라, **개입 선택기**로 쓰는 게 핵심이다.
- `failure_type=fundamental` → 모델을 믿지 말고 **L1+L3(결정적 검증) 우선** + 외부 근거/툴로 확정
- `failure_type=limitation` → 도메인 ContextBlock/팩을 붙이고 **L3 하네스(특화 테스트)** 로 보강
- `failure_type=robustness` → **ROBUSTNESS(transform) 팩 + RobustnessProbe** 로 흔들림을 먼저 노출하고 안정화

- 권장 taxonomy(초기 8개, 유지):
 - `context_dilution` : 길이/턴 증가로 제약 희석
 - `instruction_conflict` : 상충 지시
 - `format_leak` : 포맷 밖 텍스트/구조 누수
 - `tool_misroute` : 툴 호출 종류/시점/순서 오류
 - `overconstraint` : 룰 과잉 적용(정상 케이스 망침)
 - `underconstraint` : 룰 적용 누락
 - `distribution_shift` : 도메인/스타일 변화로 깨짐
 - `adversarial_prompting` : 교란/탈선/탈출 프롬프트

- 2축 라벨을 남기는 방법(권장, **SSOT 변경 없이**):
 - `failure_prediction.predicted_failures[*].triggers`에 태그 문자열을 추가한다.
 예: `["axis:robustness","reasoning:formal","transform:reverse_relation"]`

- (옵션, “작게” 추가할 만한 taxonomy id 3개 — 필요할 때만):
 - `reversal_curse` : 관계 역방향 질문에서 뒤집힘(§15.5 ROBUSTNESS의 reverse_relation로 쉽게 탐지)
 - `compositional_depth` : 2-hop/다중 전제 결합에서 붕괴(깊이↑/distractor↑에 취약)
 - `prompt_variation` : reword/perspective/verbosity/distractor에 민감(=robustness issue)

- 운영 팁:
 - 실패 로그(Event/Trace)에 taxonomy 라벨을 붙이면, 룰 리팩토링/회귀팩 우선순위가 빨라진다.
 - 예측은 “판결”이 아니라 “힌트”로 취급하고, 회귀/반례 테스트로 교차검증한다.

### 15.5 Micro-Regression Pack(팩) 운영 규율(권장)

- Micro-Regression은 “작고 자동 채점 가능한” 테스트다. (정규식/스키마/툴콜 여부 등)
- 팩을 미리 만들어두면, 룰 작성자가 테스트를 매번 창작하지 않아도 된다.
- 초기 추천 팩 7종:
 - **FORMAT**: JSON/YAML/마크다운 포맷 준수(스키마/정규식)
 - **TOOL**: 툴 호출 강제/금지/순서/args 스키마
 - **BUDGET**: 길이/반복/루프 감지/조기 종료
 - **NOISE**: 출력 잘림/툴 실패/부분 성공/재시도 복구/비결정성 대응
 - **ROBUSTNESS**: 의미 보존 변형(transform)에서 **불변식 유지**(=숨은 취약성 노출)
 - **ENV**: 샌드박스/하네스 재현성(시드/반복 실행) + 플래키 감지
 - **CONTEXT_LEARNING**: 문서/룰/SDK/스펙 컨텍스트에서 새 규칙/제약/파라미터를 **찾아 적용**(=binding). 가능한 한 `RegressionTestSpec.assert`(정규식/스키마/툴콜)로 결정적 채점.

#### 15.5.1 CONTEXT_LEARNING(CLPack v1) — “컨텍스트가 정답”을 실제 회귀팩(RegressionTestSpec)으로 내리기

목표: **컨텍스트에만 있는 규칙/절차/파라미터**를 모델이 실제로 사용했는지(또는 사전지식으로 덮어썼는지)를
“사람 채점” 없이 **결정적(assertion) 테스트**로 잡아낸다.

핵심 원칙(가성비):
- “의미 비교”를 하지 말고, 가능한 한 **토큰/함수명/파라미터명/ID** 같은 *검사 가능한 표면*으로 환원한다.
- 루브릭을 `RegressionTestSpec.assert`로 내릴 수 없으면, 그 항목만 L2(ContextLearningProbe)의 얇은 판정으로 보조한다.

권장 최소 세트(예: 6개):
1) **doc_required_token**: 컨텍스트가 요구하는 필수 함수/상수/키워드 포함(`regex_present`)
2) **forbidden_token**: 컨텍스트가 금지한 우회 경로/함수 미포함(`regex_absent`)
3) **required_params**: 출력 스키마의 필수 슬롯 바인딩(`json_schema`)
4) **tool_policy_off**: web 같은 금지 툴 미호출(`tool_not_called`)
5) **tool_policy_on**: file_search/sandbox 같은 필수 툴 호출(`tool_called`, 필요한 경우)
6) **multiturn_state**: 이전 turn 결과 재사용/정합성(`contains` 또는 `exact_match`)

(권장) 집계/검색 tags:
- `pack:CONTEXT_LEARNING` + `cl:*` (예: `cl:doc_binding`, `cl:prior_conflict`, `cl:param_binding`, `cl:tool_policy`, `cl:multiturn`)

예시: CLPack v1 RegressionTestSpec 템플릿
```yaml
# 1) 문서 바인딩: 필수 토큰/함수 포함
- schema_version: "0.1.0"
 test_id: "clpack_v1.doc_required_token.Safety_request_airspace"
 test_type: "regression"
 severity: "critical"
 input_ref: "clpack/drone_sdk/task1"
 assert:
 type: "regex_present"
 args: {pattern: "Safety_request_airspace\("}
 tags: ["pack:CONTEXT_LEARNING","cl:doc_binding"]
 expected: {must_pass: true, notes: "컨텍스트에 명시된 필수 함수 호출"}
 linked_rule_ids: ["rule:drone_sdk_v1"]

# 2) 사전지식/우회 경로 금지
- schema_version: "0.1.0"
 test_id: "clpack_v1.forbidden_token.DroneAirspace_access"
 test_type: "regression"
 severity: "critical"
 input_ref: "clpack/drone_sdk/task1"
 assert:
 type: "regex_absent"
 args: {pattern: "DroneAirspace_access"}
 tags: ["pack:CONTEXT_LEARNING","cl:prior_conflict"]
 expected: {must_pass: true, notes: "컨텍스트에 없는/금지된 함수로 우회 금지"}
 linked_rule_ids: ["rule:drone_sdk_v1"]

# 3) 구조적 바인딩: 필수 파라미터(슬롯) 존재
- schema_version: "0.1.0"
 test_id: "clpack_v1.required_params.flight_zone_landing_site"
 test_type: "regression"
 severity: "critical"
 input_ref: "clpack/drone_sdk/task1"
 assert:
 type: "json_schema"
 args:
 schema:
 type: object
 required: ["flight_zone","landing_site"]
 properties:
 flight_zone: {type: string}
 landing_site: {type: string}
 tags: ["pack:CONTEXT_LEARNING","cl:param_binding"]
 expected: {must_pass: true, notes: "태스크 스펙의 필수 슬롯 바인딩"}
 linked_rule_ids: ["rule:drone_sdk_v1"]

# 4) 툴 정책: web 금지(컨텍스트만으로 풀기)
- schema_version: "0.1.0"
 test_id: "clpack_v1.tool_policy.web_off"
 test_type: "regression"
 severity: "normal"
 input_ref: "clpack/drone_sdk/task1"
 assert:
 type: "tool_not_called"
 args: {tool: "web"}
 tags: ["pack:CONTEXT_LEARNING","cl:tool_policy"]
 expected: {must_pass: true, notes: "컨텍스트 러닝 측정: 외부검색 차단"}
 linked_rule_ids: ["rule:tool_policy_default"]

# 5) 멀티턴 정합성: 이전 turn 결과 재사용
- schema_version: "0.1.0"
 test_id: "clpack_v1.multiturn.contains.prev_result_id"
 test_type: "regression"
 severity: "normal"
 input_ref: "clpack/multiturn/task2"
 assert:
 type: "contains"
 args: {substring: "<prev_result_id>"}
 tags: ["pack:CONTEXT_LEARNING","cl:multiturn"]
 expected: {must_pass: true, notes: "이전 turn 합의/상수 재사용(정합성)"}
 linked_rule_ids: ["rule:working_set_state"]
```

실패 신호 연결(권장; SSOT §5.2.4):
- critical required_token/required_params 실패 → `CONTEXT_LEARNING:NOT_LEARNED`
- 절차/예외 등 non-critical 누락 → `CONTEXT_LEARNING:INCOMPLETE`
- prior_conflict 컨텍스트에서 forbidden_token 등장 → `CONTEXT_LEARNING:PRIOR_KNOWLEDGE_OVERRIDE`
- 멀티턴 state 검사 실패 → `CONTEXT_LEARNING:TURN_DEPENDENCY_BROKEN`

주의:
- CLPack은 hot-path 상시 실행용이 아니다. **offline regression + canary**로만 굴려 정책/주입을 고친다.
- CLPack 컨텍스트가 fictional/modified knowledge(오염 방지용)인 경우가 많다. 여기서 얻은 ‘사실’을 전역 메모리/룰로 승격하지 않는다.

- **ROBUSTNESS(transform) 팩** 권장 최소 변형(2602.06176의 관찰을 운영형으로 내린 것):
 - `transform:reword` / `transform:perspective` / `transform:verbosity`
 - `transform:distractor` (무관 정보 삽입)
 - `transform:reverse_relation` (reversal curse 탐침)
 - `transform:order_shuffle` (순서 편향 탐침)

- 채점은 “완전 의미 비교”를 하려 하지 말고, **결정적 불변식**으로 얇게 간다(가성비):
 - JSON 스키마/필수 필드(must_have) 유지
 - 필수 툴 호출 여부/순서
 - 최종 숫자/선택지/코드 실행 결과(가능하면 L3)

- counterexample는 팩과 별도로 “클러스터형 1 + 경계형 1”을 최소 규율로 둔다.

### 15.6 FlowMap 정책 튜닝(권장)

- **Replay → Canary → Rollback** 순서로만 반영한다(룰 승격과 동일한 운영 규율).
- Replay(오프라인): 기존 로그로 `Risk/Opportunity/efficiency`를 산출하고, 정책 변경안으로 결과(FAIL/UNKNOWN, cost/latency)를 재생 비교한다.
- Canary(온라인): 버킷/impact 일부에만 적용하고, 악화 시 **정책만 즉시 롤백**한다.
- 주의: FlowMap은 상관 기반 지도다. 인과는 A/B(정책 on/off), 개입 강제/차단 같은 반사실 비교로 보정한다.
- (옵션) `FlowMapSnapshot.estimator`로 학습된 추정기(nn_field)를 쓰더라도, **반사실 비교 + 롤백 규율**은 더 엄격해져야 한다(추정기 과신 금지).
- (옵션) `cat_flow_map_v1`(Categorical Flow Maps) 같은 범주형 추정기를 쓰면, guidance(재가중) 파라미터(예: β)와 reward 정의가 **정책 그 자체**가 된다. 따라서 β/보상 정의도 replay→canary로 고정하고, 런타임 즉흥 변경은 금지(드리프트/회귀 불가).

## 16) 오픈소스 공개 체크리스트 (GitHub)

### 16.1 기본 정책
- Default는 **Untrusted**
- Trusted는 명시적 opt-in(예: `RULECRAFT_TRUSTED=1`)

### 16.2 저장소 구조(권장)

```
rulecraft/
 src/rulecraft/ # core (의존성 최소)
 runner/
 rulebook/
 validator/
 logging/
 policy/ # trusted/untrusted, lint, conflict
 compactor/
 compose/
 adapters/
 local/
 api/
 examples/
 minimal_runner.py
 local_quickstart.py
 api_quickstart.py
 docs/
 ARCHITECTURE.md
 SECURITY.md
 tests/
```

### 16.3 공개 전 문서 최소 세트
- README.md (60초 Quickstart)
- ARCHITECTURE.md
- SECURITY.md
- CONTRIBUTING.md
- LICENSE
- CHANGELOG.md
(+ 가능하면 CODE_OF_CONDUCT.md)

### 16.4 CI 최소 테스트(생존형)
- rule lint 테스트(무력화/유출/권한 상승 패턴)
- conflict check 테스트
- runner smoke test(examples가 끝까지 돈다)

---

## 부록 A) 운영 기본값 표 (초기 권장)

| 항목 | 로컬 기본 | API 기본 |
|---|---:|---:|
| K_probe | 3 | 3 |
| K_full | 6 (동시성/속도 고려) | 6 (비용 고려) |
| frontier band (p_lb95) | 0.3~0.7 | 0.3~0.7 |
| deadzone (p_lb95) | < 0.05 | < 0.05 |
| compose 조건 | high impact 또는 frontier | high impact 또는 frontier |
| 재시도 | 1회(대부분 의미 적음) | 2~3회(백오프+jitter) |

> 이 값들은 “시작점”이다. 실제 운영 로그를 보고 조정한다.

---

## 부록 B) 메타데이터 표준 예시

```json
{
 "schema_version": "0.1.0",
 "run_id": "t_01H...",
 "input_ref": "xhash_01H...",
 "bucket_id": "I2|coding|clarity_med",
 "run_tags": ["heavy-thinking", "tool-heavy"],
 "applied_rules": [
 {"rule_id": "core.g1", "version": "0.1.0", "type": "GuardrailRule"},
 {"rule_id": "proj.s3", "version": "0.1.0", "type": "StrategyRule"}
 ],
 "run": {
 "mode": "kroll",
 "cfg": {"temperature": 0.2, "seed_prompt": "jitter_v1", "self_refine_steps": 0}
 },
 "outputs": {
 "output_ref": "yhash_01H...",
 "draft_summary": null,
 "self_review_signals": null,
 "compose_inputs": {"used_run_ids": null, "used_summary_ids": null}
 },
 "validator": {"validator_id": "vf_l1l2_v1", "verdict": "PARTIAL", "outcome": "UNKNOWN"},
 "cost": {"latency_ms": 1830, "tokens_in": 1240, "tokens_out": 420, "tool_calls": 1}
}
```

---

## 부록 C) 용어 미니 사전

- **Orchestrator**: 전체 파이프라인을 실행하는 상위 루프
- **BackendAdapter**: 로컬/API 백엔드를 동일 인터페이스로 추상화
- **Validator**: 결과의 제약 준수/근거/형식 등을 판정
- **K-drafts**: 다회 생성(또는 다경로 탐색)으로 신뢰도 추정
- **SummaryBuilder**: 롤아웃 결과를 짧은 요약으로 압축
- **Composer**: 요약 묶음을 보고 최종안을 통합 생성
- **Rulebook**: 규칙 저장+운영(권한/승격/회귀)의 중심

- **SelfReview-1pass**: 단일 호출에서 “질문/반박/관점전환/통합” 절차를 강제하는 중간 티어 추론 스캐폴딩
- **SSOT**: 계약/스키마/설계 결정에서 “단일 진실원천”으로 취급되는 정의(문서 또는 파일)
- **Regression**: 룰/행동의 품질을 유지하기 위한 회귀 테스트

## 부록 D) DataPrep Domain Pack — LLM 기반 데이터 준비(정리/통합/보강) 운영 패턴 (TKDE 2025; arXiv:2601.17058)

이 부록은 “LLM을 데이터 준비에 쓰는” 케이스를 Rulecraft 관점으로 번역한 운영형 가이드다.
핵심은 한 문장: **로컬 문맥은 LLM, 전역 제약/검증은 하네스(L3)** 로 분업한다.

### D.1 작업 분류(권장) — bucket/domain/shard를 고정해 로그를 쌓기
- `domain_tag = "data_prep"`
- `shard`(권장):
 - `cleaning` (standardization / error_processing / imputation)
 - `integration` (entity_matching / schema_matching)
 - `enrichment` (annotation / profiling)

이 분류는 “정답”이 아니라 **관측/회귀/비용정책**을 위한 라벨이다.

### D.2 기본 파이프라인(권장) — 표 전체를 프롬프트에 넣지 않는다
1) **샘플링**: 대표 row/column 샘플만 뽑는다(프롬프트 예산 절약).
2) **전역 신호 계산(SandboxProbe/L3)**:
 - null/unique/분포/타입/기본 통계
 - (가능하면) 단순 제약: NOT NULL, UNIQUE, REGEX, DOMAIN, FK 후보
3) **제안 생성(LLM)**:
 - 변환은 가능한 한 **재실행 가능한 코드(pandas/sql/regex)** 로
 - 적용 범위 + before/after 예시 + 롤백 단위 포함
4) **실행 검증(Validator L3: DataPrepHarness)**:
 - 변환 적용 후 제약 위반/row count/스키마 변경 확인
 - integration이면 symmetry/transitivity 불변식 확인
5) **적용(옵션)**: canary(부분 적용) → replay 지표 확인 → rollout
6) **로그/회귀**: 실패는 `violated_constraints`로 키를 고정해 쌓고, 회귀팩으로 편입

### D.3 “자주 터지는” 실패와 표준 키(권장)
- `DATA_PREP:SCOPE:GLOBAL_VIEW_REQUIRED`
 - 로컬 컨텍스트로만 고치려다 전역 제약/통계가 필요한 상태
- `DATA_PREP:CONSTRAINT:VIOLATION[:<type>:<field>]`
- `DATA_PREP:INTEGRATION:SYMMETRY_BROKEN`
- `DATA_PREP:INTEGRATION:TRANSITIVITY_BROKEN`
- `DATA_PREP:ENRICHMENT:UNSUPPORTED_CLAIM`

이 키들은 **집계/FlowMap/회귀팩**의 접착제다(자유서술 금지).

### D.4 평가(ValidationResult.score_evidence.data_prep 권장 슬롯)
데이터 준비는 “좋은 글”이 아니라 “좋은 데이터”가 목표라서, 평가도 다차원이어야 한다.

- correctness: accuracy / precision / recall / f1 / matching_rate
- robustness: ROC/AUC (이상치/오류 탐지류에서)
- ranking: P@k / MRR / Recall@GT / HitRate (retriever+reranker류에서)
- semantic preservation: ROUGE / cosine similarity (요약/설명/메타데이터 드리프트 탐지)

가능하면 `score_evidence.data_prep.metrics`로 기록해두면, 나중에 “비용 대비 개선”이 측정 가능해진다.

### D.5 micro-regression 팩(제안) — data_prep_v1
- **DP_CONSTRAINTS**: UNIQUE/NOT NULL/REGEX/DOMAIN/FK 같은 제약 위반이 없는지(L3 기반)
- **DP_DIFF**: 허용되지 않은 컬럼/row가 바뀌지 않았는지(스키마/row count 포함)
- **DP_INTEGRATION_INVARIANTS**: symmetry/transitivity
- **DP_ENRICHMENT_GROUNDING**: 증거 링크가 없는 주장 탐지(FGFC 또는 evidence 규칙)

### D.6 ContextBlock(선택적 주입) 최소 세트(요약)
CU는 “정답”이 아니라 **실패를 예방하는 난간**이다.
- `cb_dp_global_stats_first_v1` (전역 통계 먼저)
- `cb_dp_no_hallucinated_imputation_v1` (근거 없으면 보류)
- `cb_dp_integration_invariants_v1` (대칭/추이 불변식)
- `cb_dp_transform_must_be_replayable_v1` (diff+rollback 가능 변환)

자세한 포맷은 `RC_ContextBlock_Spec_r02.md`의 data_prep 예시를 따른다.

## 17) 구현 체크리스트 (바로 붙이는 순서)

1) **Orchestrator/BackendAdapter/Logger**부터 고정
 - LLMAdapter meta: `model/backend/latency_ms/tokens_in/out/cost_usd/error`(Playbook §4)
 - RunLog 최소 필드: `run_id, applied_rules, verdict/outcome, cost`(Playbook §11, Addendum §3.4)

2) **ValidationResult를 SSOT 계약으로 고정**
 - `verdict/outcome/reason_codes/(violated_constraints)` 구조(=Addendum §3.3)
 - PASS 판정은 `verdict==PASS && outcome!=FAIL`로 단일화(Addendum §5.1)

3) **should_escalate + BudgetController**를 “옵션”이 아니라 “상한 제어 장치”로 둔다
 - high impact 최소 보험 계산(`K_probe` 또는 SelfReview-1pass) 남기기(Playbook §6.4)
 - 나머지 버킷에서 먼저 감산하는 단계형 정책(Full→Probe→1-pass)

4) **DraftSummarizeCompose-lite(요약→compose)**는 처음부터 넣는 게 낫다
 - rollout을 만들어놓고 안 쓰면 비용만 늘어난다(Playbook §6.3.1)

5) **룰 승격 게이트(temporary→active)**는 초기에 빡세게
 - tests 없으면 무조건 temporary(Playbook §15.2, Addendum §6.3)
 - 최소: regression ≥1 + counterexample ≥2(클러스터 1 + 경계 1)

6) **FlowMap은 마지막에**
 - 로그가 쌓인 뒤 replay→canary→rollback으로만(Playbook §15.6, Addendum §3.8)
