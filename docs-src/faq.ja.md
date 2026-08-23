# よくある質問

## kogo は PDF をどこかに送信しますか?

いいえ。CLI・ライブラリ・セルフホストのWebアプリのいずれを使っても、すべての処理は
ローカルで行われます。[公開デモ](https://kogo-demo.tatu-sec.dev/) は同じオープンソース
コードを利用した便宜的なデプロイであり、使いたくない場合はセルフホストしてください。

## テキスト情報のないスキャンPDFを比較できますか?

単語単位の精度では比較できません — スキャンのみのPDFには抽出できるテキストがないため、
視覚的な比較(図・レイアウト)のみが行われます。単語単位のテキスト差分が必要な場合は、
先に(例えば `ocrmypdf` などで)OCRテキストレイヤーを追加してください。kogo自体への
OCR対応は [ROADMAP.md](https://github.com/ta-061/kogo/blob/main/ROADMAP.md) で
検討中です。

## パスワード保護されたPDFに対応していますか?

いいえ — 先にパスワードを解除してください。`compare_pdfs` はこの場合(および
破損・空・過大なファイルなど他のユーザー起因の問題の場合)に `ComparisonError`
を送出します。

## 移動した段落が「移動」ではなく「削除+追加」として報告されるのはなぜですか?

完全一致行のマッチング([仕組み](architecture.ja.md#text-diff)を参照)は、
*変更されていない*テキストが移動した場合はすでに抑制しています。編集と移動の
両方が行われた段落には、マッチさせるためのバイト単位で同一な行が存在しないため、
現状では旧位置での削除と新位置での追加として報告されます。専用の移動テキスト検出は
[ROADMAP.md](https://github.com/ta-061/kogo/blob/main/ROADMAP.md) で追跡しています。

## マーカー付きPDFを書き出さずに kogo を使うには?

`kogo.compare_pdfs(..., artifacts=False)` を使います —
[CI連携のレシピ](recipes/ci-integration.ja.md) を参照してください。

## バグ報告や機能要望はどこに出せばいいですか?

[GitHub Issues](https://github.com/ta-061/kogo/issues) のバグ報告または
機能要望のテンプレートを使ってください。一般的な質問には
[Discussions](https://github.com/ta-061/kogo/discussions) を使ってください。
セキュリティ上の脆弱性については
[SECURITY.md](https://github.com/ta-061/kogo/blob/main/SECURITY.md) を参照し、
公開のIssueには投稿しないでください。
