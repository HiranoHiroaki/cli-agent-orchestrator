# Deterministic Runner デバッグ運用ガイド

## 1. 目的
- 本ガイドは、deterministic runner のデバッグを「安全に・低コストで」行うための運用手順を定義する。
- 重要方針:
  - 通常運用ではデバッグを無効化する
  - AI入力にデバッグ生ログを渡さない
  - 必要なときだけ、必要なアンカーだけを有効化する

## 2. デフォルト運用（本番）
- `RUNNER_DEBUG=0` を既定とする（未設定でも無効）。
- AIへ渡す情報は `cao deterministic show-task --view agent` のみ利用する。
- `show-task` の human view や生ログ（stdout/stderr/apply_log）は、AI入力に直接貼り付けない。

## 3. 一時的にデバッグを有効化する
### 3.1 全アンカー有効化（短時間のみ）
```powershell
$env:RUNNER_DEBUG="1"
```

### 3.2 アンカーを限定有効化（推奨）
```powershell
$env:RUNNER_DEBUG="1"
$env:RUNNER_DEBUG_ANCHORS="dispatch.start,dispatch.end,gateway.queue.reject,evidence.fail_closed"
```

### 3.3 無効化に戻す
```powershell
Remove-Item Env:RUNNER_DEBUG -ErrorAction SilentlyContinue
Remove-Item Env:RUNNER_DEBUG_ANCHORS -ErrorAction SilentlyContinue
```

## 4. 推奨アンカーセット
- dispatch観測:
  - `dispatch.start`
  - `dispatch.end`
  - `dispatch.timeout`
- gateway観測:
  - `gateway.health.ok`
  - `gateway.probe.ok`
  - `gateway.queue.reject`
- fail-close観測:
  - `evidence.fail_closed`
  - `patch.apply.failed`
  - `patch.apply.success`

## 5. AIトークン消費を抑えるルール
- デバッグログ全文をAIに投入しない。
- AIに渡すのは:
  - 状態
  - 理由コード
  - 次アクション
  - 必要最小のイベント要約
- 具体的には `--view agent` 出力を基準とし、補助的に人間がログを読む。

## 6. 障害時の標準手順
1. `show-task --view agent` で現状態と直近イベントを確認。
2. 必要なアンカーだけ有効化して再実行。
3. `LOCAL_MODEL_BUSY` / `LOCAL_MODEL_TIMEOUT` / `MISSING_EVIDENCE` のいずれかに分類。
4. 原因確定後は必ずデバッグ変数を無効化して通常運用に戻す。

## 7. 禁止事項
- `RUNNER_DEBUG=1` の常時運用。
- 複数人運用でアンカー無制限有効化のまま放置。
- AIへの生ログ丸投げ。

