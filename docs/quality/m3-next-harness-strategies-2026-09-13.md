# M3 Persona / Tavern 下一轮 Harness 策略冻结（2026-09-13）

本记录以已查明的 Scene 502 为起点：历史四个 502 都是应用把 HTTP 200 的截断或严格 Scene DTO 失败映射为 502，不是 upstream 502。对应额度与 bounded repair 已修复；Tavern actor protected snapshot v2 的 claim epoch、权威投影和失败终态也已独立复核。下一轮不继续围绕 HTTP 状态调 prompt，而是把内容语义实验拆成两个互不借用结果的 provider-free readiness gate。

Persona Source Constraint Capsule 已按预注册失败（strict pair 6/8，并出现 candidate-only permission/shared-history major）。因此下面两项不复用 capsule family、输出或评分，不是 Tavern transfer，也不改变 production Harness registry。readiness 通过最多允许另行冻结 live shadow；它不是模型质量、生产 promotion、Persona 保存或 Tavern commit 语义认证。

## A. Tavern-native counterfactual twins

版本冻结为 `tavern-counterfactual-twins-readiness-v1`。固定 10 个全新 family，覆盖 permission、relationship、shared history、epistemic provenance、Scene/world state 各两例。family ID、axis、第二侧 polarity、权威层和唯一翻转原子已逐项写入机器文件；每个 axis 恰有一例 DENY、一例 EXPLICIT_UNKNOWN。fixture 必须逐项实现这些原子，并在校准前的独立 commit 绑定 source/projection/oracle digest；拒绝重复 digest、相同规范化原子或与列出的历史 campaign family/source digest 重合。每例只执行 direct 首步的研究投影；Room、Participant、Scene、roster、transcript、user turn、schedule 和 reply anchor 都是人工 committed-shape 输入，不运行 Persona/Scene generation。

每个 family 有 SUPPORT 与已冻结的 DENY 或 EXPLICIT_UNKNOWN twin。用户消息及除一个权威语义原子外的规范化 Tavern projection 必须逐字一致；派生 digest、坐标、delta 元数据、axis 与 polarity 必须从 generator-visible payload 物理删除，不只是提示模型忽略。冻结记录必须包含唯一 `allowed_delta_json_pointer`、两侧 canonical value、Unicode code-point/UTF-8 byte span 和 canonical SHA-256。构造器发现第二处差异即 fail closed。UNKNOWN 要求明确保留不确定，DENY 要求纠正；每侧 gold reply 都要保留冻结的非拒答任务内容并只在 claim-response span 上变化，always-deny、always-agree、always-refuse 与 generic reply 都失败。

provider-free gate 固定为：10/10 family、20/20 pristine twin 无 issue；每 twin 固定 `quoted_opposite_literal` 与 `explicit_denial_of_opposite` 两个 hard-negative，各只改一个 reply span、expected issue 为空、内容 digest 不得重复，共 40/40 无误报；每 family 固定六项 mutation：`extra_authoritative_delta`、`declared_delta_pointer_mismatch`、`source_codepoint_span_shift`、`source_utf8_span_shift`、`source_slice_digest_mismatch`、`canonical_world_digest_mismatch`，分别只能命中同名稳定 error code，共 60/60。每 family 另有 exact `pair_copy_reply`、人工预作者的 `surface_paraphrase_copy` 与 `nonce_decorated_copy` 三个 insensitivity control，均必须只命中 `counterfactual_insensitivity`，共 30/30；后两者的语义等价由 sealed oracle 和 fixture reviewer 确认，不声称自动通用释义能力。source/digest/坐标/allowed-delta 任一篡改全部 fail closed。family 是唯一统计单位，20 twins 与 control/mutation 不扩张分母。任一 data、grader、metric、infrastructure、uncertain 或 fixture review 缺失使该 family 失败但仍留在 10 的分母，不补 family。

两名只参加 Tavern、互不读取输出的隔离 fixture reviewer 需确认 10/10 fixture/oracle 无歧义。执行 adapter/generator 只能读 public source/projection，不能读 sealed oracle、expected marker、mutation、issue code、key 或 builder secret；离线 deterministic grader 在 run freeze 后可读 sealed oracle与输出，但不能生成候选；packet builder 在 run freeze 后读 allowlisted evidence 与 oracle；aggregator 才能读三个 anchor、事前冻结的 builder/aggregator、oracle、packet/key 和 review。provider-free readiness 不包含模型输出盲评；未来 live 的 blind-output reviewer 必须在另一个 live prereg 中指定，且与 fixture reviewer 集合不相交。旧 conditional Tavern repair 会把 `case.gold` 中的 expected requirements 放进 prompt，明确禁止复用。未来盲包隐藏 family、axis、polarity、状态和 A/B 映射；任一侧不可用时整个 family 使用字节相同 sentinel。

当前提交只是 design anchor，并冻结两个唯一 campaign ID：`tavern-counterfactual-twins-readiness-20260913-v1` 与 `persona-claim-ledger-readiness-20260913-v1`。fixture/oracle、historical semantic ancestry/dedup manifest、canonical golden vectors、validator/mutation/packet-key builder/aggregator 源码与规则、dependency lock、runtime image/interpreter、entrypoint、argv、完整 config digest 和环境 allowlist 必须在任何 calibration 或 live wire 前由后续 prereg commit 绑定。readiness/calibration/rebuild 必须 hermetic：无网络、无 wall-clock/random/env 输入（冻结 seed 与显式 allowlist 除外）、无未列文件读取，并把实际输入摘要写入重建证据。

每个 campaign ID 只能在作者不可回写的 append-only CI/外部见证 ledger 接受第一次 prereg。任何第二次 prereg、重复或 unmatched runner admission、abandonment、未记录 execution、依赖/runtime/config 漂移都直接使整个 campaign terminal `readiness_failed`；它们不创造额外 family 分母，也不能另挑一条全绿链。run manifest/admission 必须绑定并验证 first-attested prereg SHA，缺失时 fail closed。仅本地 commit、tag、时间戳或 ancestry 都不证明事前冻结。

运行完成后的第二个 frozen-run commit 只能绑定 manifest/report 与逐 sample allowlisted raw evidence，不能修改前一个 commit 的 fixture、oracle、builder 或 aggregator。fixture review 完成后第三个 review-evidence commit 绑定确定性重建的 review packet/key、两份 reviewer 原始文件、reviewer 身份/隔离 attestations、raw/canonical SHA；aggregator 必须与 first-attested prereg 中的 digest 一致。每名 reviewer 的独立交付通道必须在作者读取正文之前，把 `campaign_id + prereg_sha + reviewer_task_id + raw_bytes_sha256` 写入作者不可回写的 append-only 外部见证；不接受事后创建 key 的签名替代。第三 commit 只能收录这些已见证字节。最终 aggregate 只能从恰好三个指定 commit 以冻结的 hermetic runtime 重建。aggregator 校验两个外部见证、Git ancestry 和逐阶段 allowlist，并拒绝单侧 sentinel、重复 case/reviewer、同体 review、packet/key 联合作伪、替换 review body 和可评子集统计。SHA 只提供完整性；事前外部见证、分阶段 commit 与隔离访问边界共同防止后验联合改写。

Production v3 的 Tavern Message commit evidence 仍只证明 `primary_output_only` 的单条 Message projection。Run/Step 状态、幂等、授权 snapshot 与 read-back 是另行核对的 operational evidence，不由该 commit policy 证明全部事务副作用。counterfactual policy、oracle、mutation code 和人工评分不得进入 v3 trace、commit evidence、API/OpenAPI 或 safe manifest。

## B. Persona Explicit Semantic Claim Ledger

版本冻结为 `persona-explicit-semantic-claim-ledger-readiness-v1`。研究包装为 `PersonaClaimLedgerProposalEnvelopeV1`，内部包含原生产 `PersonaCardBatchContentProposalV1` 与 research-only `PersonaProposalClaimReceiptSidecarV1`。不得修改生产 proposal、`PersonaProfile` 或公共 API。

Ledger 由人工/应用拥有，绑定原始 source bytes 的 SHA-256、明确的 `unicode_code_point_v1` 与 UTF-8 byte 坐标、typed semantic key、qualifier 和一个或多个 source span。claim state 只有 `asserted | denied | explicitly_unknown`；来源未提及不是 unknown。claim ID 由应用按 source digest、semantic key、state、qualifier 与排序 spans 的 canonical bytes 分配，模型只能引用，不能创建 ID 或坐标。多个 claim 可以共享 source span，不能照搬 Capsule 的禁止重叠规则。

Sidecar 是 model-owned 自述，不是 Harness/domain receipt。它绑定 canonical proposal digest；每项引用 proposal JSON Pointer、leaf-local code-point/UTF-8 span、slice digest、零个或多个 ledger claim ID 和 `assert | deny | preserve_unknown | unsupported`。结构合法矩阵为：`asserted × assert × one-or-more matching refs`、`denied × deny × one-or-more matching refs`、`explicitly_unknown × preserve_unknown × one-or-more matching refs`，以及 `unsupported × zero refs`；其他组合全部拒绝。结构合法不等于 candidate 合格：任何 `unsupported` receipt 都 fail closed 为稳定 `unsupported_semantic_assertion`，pristine、readiness 和未来 live candidate 的允许数均为零。应用从结构推导检查，模型不得声明权威 `supported=true`。来源未提及不能创建 unknown claim；`unsupported` 不能与 unknown 合并，也不是允许自由发挥。确定性校验无法证明 receipt 完整或语义诚实，必须另做人工复核。

固定且不得替换的八个全新 family：`ice_core_courier`、`community_darkroom`、`orchard_sensor`、`museum_audio_circle`、`ferry_tide_log`、`seed_library`、`planetarium_caption`、`river_microplastic`。它们分别覆盖多字节坐标、引语/假设、分作用域读写权限、多人物共指、时间限定、正负共同经历并存、direct/reported 认知来源，以及职业明确但资质未知。每个 family 的 required semantic key、state、qualifier 和最小 receipt 次数已经写入机器文件，不能在 fixture authoring 时降为 optional；不得改写成上一轮同构的五类否定/未知 capsule。historical ancestry/dedup manifest 必须逐 family 对照既有 Persona/Scene/Tavern corpus 的 source、semantic matrix 与 provenance，由两名 fixture reviewer 确认不是换名或近义复用。

每个 ledger claim 还冻结 `coverage = required | optional | forbid_assertion`。readiness validator 以 sealed、人工拥有且 generator 不可读的 semantic-span completeness oracle 标记冻结 provider-free proposal 中需要 receipt 的语义 spans；它不允许模型自报 `nonsemantic`，也不假定每个格式字符串都是语义 claim。该 oracle 只校准这些冻结 canned proposals，不外推到未知 live output。未来 live 必须另行预注册 output-independent extraction rule，并让独立 blind reviewer 对每个实际 proposal 做 span completeness 审阅，原始 review 仍需作者读取前外部见证。通用空壳、拒答、遗漏 required claim、未覆盖 oracle semantic span 或任何 unsupported assertion分别命中 `proposal_information_loss`、`semantic_leaf_receipt_coverage_missing` 或 `unsupported_semantic_assertion`，不能靠少写内容过门。

provider-free control 按 family 固定为两例 `quoted_or_hypothetical_literal`、两例 `explicit_denial_literal`（均 expected issue 为空），两例 `generic_shell`、两例 `refusal_shell`（均 expected `proposal_information_loss`）；每项只改一个冻结 span，control 内容 digest 不得重复。gate 要求这 8/8 命中各自预期。另有每 family 21 个固定 mutation 即 168/168 精确命中唯一 code。机器清单逐项冻结：`schema_extra_field`、`source_state_enum_invalid`、`source_sha_mismatch`、`source_codepoint_span_mismatch`、`source_utf8_span_mismatch`、`source_slice_digest_mismatch`、`duplicate_claim_id`、`claim_id_collision`、`contradictory_semantic_key`、`unknown_has_concrete_value`、`proposal_digest_mismatch`、`proposal_json_pointer_invalid`、`proposal_codepoint_span_mismatch`、`proposal_utf8_span_mismatch`、`unknown_claim_reference`、`duplicate_claim_reference`、`illegal_state_use_relation`、`unsupported_semantic_assertion`、`semantic_leaf_receipt_coverage_missing`、`overlapping_receipt_span`、`duplicate_receipt`。测试内层错误时必须重算外层 seal。两名只参加 Persona、互不读取输出且与 Tavern fixture reviewer 集合不相交的隔离 fixture reviewer 需确认 8/8 ledger/source/coverage/control 无歧义，任一失败仍保留在八分母；未来 live blind-output reviewer 另行预注册且不得属于任一 fixture reviewer 集合。

未来若另行冻结 live paired gate，至少要求：八对全分母、至少 7/8 双臂 strict 且 candidate sidecar strict；至少四个 case×axis major reduction 被两人共同确认；任一 reviewer 的 candidate-only major 为零；candidate 的 relationship、permission、profession、shared history、epistemic major 均为零；false-supported、false-unknown、required-claim omission、generic/refusal information loss major 均为零。语义盲包只放 source 与匿名 proposal，隐藏 ledger/receipt 和 arm；receipt 使用独立 candidate-only audit 包。failed、uncertain、missing sidecar 不重跑、不补样本。

Persona adapter/generator 只能读原始 source 与 ledger 的 prompt projection（claim ID、typed semantic key、state、qualifier、source text），不能读 coverage role、semantic-span completeness oracle、control/mutation、issue code、review key 或 expected result；offline validator/grader 在 output freeze 后读完整 ledger、coverage/completeness oracle和输出；mutation builder只在 provider-free calibration 读 fixture/oracle，不可被 live adapter 导入；paired semantic reviewer 只读 source+匿名 proposal，candidate-only receipt reviewer 只读匿名 proposal+receipt+ledger audit packet；aggregator 才可读取三个 anchors、builders、oracles、packets、keys 与 reviews。

两项坐标与 digest 共用明确字节规范：原始 source bytes 必须是严格 UTF-8、拒绝 BOM/无效序列且不做 trim 或 Unicode normalization；code-point offset 为 Python/Unicode scalar 的零基、左闭右开索引，UTF-8 offset 为同一原始字符串编码后的零基、左闭右开字节索引。JSON 输入先用 duplicate-key rejecting parser，再以 UTF-8、sorted keys、无空白、`ensure_ascii=false`、`allow_nan=false` 编码；数组保持顺序，整数十进制，不允许 float。JSON Pointer 使用 RFC 6901 `~0/~1` 解码并拒绝非 canonical escape。后续 prereg commit 必须冻结跨 ASCII/CJK/emoji/combining-mark 的独立 golden vectors；validator 与 mutation builder 不能只互相验证。

Persona proposal 的 commit evidence 保持 `not_applicable`。用户后续 POST/PATCH 保存、revision、持久化与 read-back 仍是独立应用边界。provider-free readiness 通过不授权保存 Persona、接入 Tavern 或修改 production registry。

## 明确拒绝

- 复用 Capsule、confirmation 或 Scene closed-world family，或做近义改写冒充新 family；
- same-draft repair、critic、多候选或 Persona→Tavern transfer 混入同一实验；
- generator/adapter 能读取 gold、mutation、issue code、review key 或 forbidden literal；
- 把模型 claim receipt 当语义真值或 Harness commit/effect receipt；
- source 建坐标后 `.strip()` 或 Unicode normalize；
- 单侧 unavailable、删除失败、失败后补样本/追加 wire或后验修改门；
- 用 exact marker、mutation、digest、fake commit 或 provider-free 全绿宣称 M3 内容质量或 production promotion。

两项策略均经过互相隔离的只读子智能体审阅；审阅指出的 P1/P2 已纳入上述边界。下一实现步是按机器冻结文件编写 fixture、validator、mutation calibration 与盲包重建测试；在这些 readiness gate 完成并再次独立复核前，不发新的 live provider wire。
