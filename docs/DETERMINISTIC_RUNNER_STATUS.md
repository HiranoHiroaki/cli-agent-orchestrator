# Deterministic Runner 状況整理

## 1. 目的（再確認）
- やりたい体験はシンプルな1本線:
  1. 人が依頼
  2. 指示AIが段取り
  3. Ollama/MCP実行
  4. 結果要約
  5. 次アクション継続
- その裏で Runner が安全制御だけ担当:
  - 状態遷移の単一管理
  - write の fail-closed
  - 証跡の保存

## 2. 現在スナップショット（2026-05-28）
- フォーク元: `awslabs/cli-agent-orchestrator`
- フォーク先: `HiranoHiroaki/cli-agent-orchestrator`
- 作業ブランチ: `codex/deterministic-runner-foundation`
- PR: Draft `#1`
- `main` 保護: 有効（PRレビュー + required check）

## 3. 実装済み（完了）
1. Dispatch 層:
- `src/cli_agent_orchestrator/deterministic_runner/dispatch.py`
- Codex/Claude 実行アダプタ + lane timeout 反映

2. ロック:
- `src/cli_agent_orchestrator/deterministic_runner/lock_manager.py`
- repo/file lock（DB + lock file）

3. 過負荷/タイムアウト遷移:
- `src/cli_agent_orchestrator/deterministic_runner/gateway.py`
- `LOCAL_MODEL_BUSY` 即 reject（待機ループなし）
- `LOCAL_MODEL_TIMEOUT` 遷移接続
- `openziti/llm-gateway` 向け sidecar probe 接続（`/health`, `/v1/chat/completions`）

4. 状態機械と失敗可視化:
- `src/cli_agent_orchestrator/deterministic_runner/state_machine.py`
- 失敗状態をDBイベントで明示記録

5. patch 承認フロー:
- `src/cli_agent_orchestrator/deterministic_runner/db.py`
- `PROPOSED -> APPROVED -> APPLIED` 管理
- apply失敗時 `FAILED_CLOSED`

6. test-runner MCP allowlist:
- `src/cli_agent_orchestrator/deterministic_runner/test_runner_mcp.py`
- allowlistキー以外を拒否

7. CIと保護:
- `.github/workflows/deterministic-runner-checks.yml`
- required status check: `deterministic-runner-checks`

## 4. いらないものの可否（見直し結果）
### 残す（必要）
1. `state_machine.py`:
- Runner単独制御の中核なので必須
2. `db.py` の証跡管理:
- fail-closed運用の監査根拠として必須
3. `lock_manager.py`:
- 並行write事故防止のため必要
4. `test_runner_mcp.py` allowlist:
- MCP実行境界の最低限として必要
5. read-only MCP ポリシー:
- deterministic dispatch 時に `allowed_tools` と `mcp_servers` を強制検証
- `repo-read` 以外を fail-close

### 条件付きで残す（運用限定）
1. `debug.py` のアンカー:
- 開発/障害解析では有用
- ただし「AI入力へ混ぜない」が前提
- `RUNNER_DEBUG=0` を通常運用の既定とする

### いまは止める/後回し（不要寄り）
1. AIに生ログを渡して解釈させる運用:
- トークン浪費と誤解釈を招くため不採用
2. debugアンカーの常時出力:
- 本番では不要（必要時のみON）
3. gateway実装の過度な機能拡張:
- まず `openziti/llm-gateway` 直結の最小機能を優先

## 5. 現在の懸念と対処方針
### 懸念A: evidence不足チェックが遷移点依存
- 現状は sensitive transition 中心のチェック
- write系経路に抜け穴がないか再点検が必要

### 対処方針
1. `APPROVED` / `APPLIED` 直前でも evidence 完全性を強制
2. 不足時は必ず `FAILED_CLOSED` に統一
3. 理由コードを固定 (`MISSING_EVIDENCE:*`) して運用判断を単純化

### 懸念B: 制御ログがAI文脈を汚す
- RunnerログとAI入力を分離
- AIには「要約済み実行結果」のみ渡す
- アンカー/監査ログは人とRunnerのみ参照
- `show-task --view agent` で安全化した最小ビューを返す

## 6. 直近タスク（整理版）
### P0（次に実施）
1. evidenceチェックの write経路強制: 実装済み
2. AI入力ペイロード最小化（監査ログ遮断）: 実装済み（agent view）
3. debugの既定OFF運用をドキュメント化

### P1（次ステップ）
1. `openziti/llm-gateway` 実接続: 実装済み（probe）
2. lane別 reject/timeout をE2E確認: 未完（統合テストが残り）

### P2（その次）
1. MCP read-only プロファイル固定 (`repo-read` のみ): 実装済み（dispatch policy）
2. write系MCPの拒否監査ログ追加: 実装済み（policy block event）

## 7. 受け入れ条件との対応
- 状態遷移はRunnerのみ: 達成
- 過負荷時即reject: 達成
- 失敗状態をDBへ明示記録: 達成
- prompt/constraints/decision/patch/log証跡: 実装済み（追加強化予定あり）
