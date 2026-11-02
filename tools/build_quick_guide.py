"""Make the quick guide that goes in each download: one page of English, one of Japanese.

    python tools/build_quick_guide.py <output.pdf> [windows|mac]

Uses PyMuPDF and its built-in Japanese font, like the student reports.
"""

from __future__ import annotations

import sys

import pymupdf as fitz

CSS = """
* { font-family: sans-serif; color: #1f2937; }
h1 { font-size: 22pt; color: #2563eb; margin: 0 0 4pt 0; }
h2 { font-size: 13pt; color: #2563eb; margin: 13pt 0 3pt 0; }
p, li { font-size: 10.5pt; line-height: 1.4; margin: 2pt 0; }
"""

ENGLISH = """
<h1>CAM2 Exam Grading</h1>
<p>Grade scanned exam papers one question at a time, then make a report for every student.</p>

<h2>Starting CAM2</h2>
<ol>
{start_steps}
<li>CAM2 opens in your web browser. Nothing is installed, and your papers stay on this computer.</li>
</ol>

<h2>Before you start</h2>
<ul>
<li>Your scanned papers. Scan the whole class into one PDF at the photocopier, or a few batches.</li>
<li>The paper size: A4, B5 or A3.</li>
<li>If you have one, your class list in Excel or CSV.</li>
</ul>

<h2>The five steps</h2>
<ol>
<li><b>Exam &amp; scans:</b> name the exam, choose the scans and where to save.</li>
<li><b>Set up questions:</b> draw a box around each answer on the first paper.</li>
<li><b>Match names:</b> match each paper to a student.</li>
<li><b>Grade:</b> grade one question at a time.</li>
<li><b>Review &amp; export:</b> check totals and make the student reports and Excel gradebook.</li>
</ol>

<h2>Good to know</h2>
<ul>
<li>Every grade is saved as you give it. To carry on later, choose <b>Continue a previous session</b>.</li>
<li>To stop, click <b>Quit CAM2</b> on the start screen.</li>
<li>Choose <b>How to scan your papers</b> on the start screen for scanning advice.</li>
<li>Switch between English and 日本語 at the top of the start screen.</li>
</ul>
"""

JAPANESE = """
<h1>CAM2 Exam Grading</h1>
<p>スキャンした答案を設問ごとに採点し、生徒一人ひとりのレポートを作ります。</p>

<h2>CAM2の起動</h2>
<ol>
{start_steps}
<li>CAM2はWebブラウザーで開きます。インストールは不要で、答案はこのコンピューターの中だけで扱います。</li>
</ol>

<h2>用意するもの</h2>
<ul>
<li>スキャンした答案。コピー機でクラス全員分を1つのPDFに（または数回に分けて）スキャンします。</li>
<li>用紙サイズ：A4、B5、A3のいずれか。</li>
<li>クラス名簿（ExcelまたはCSV、あれば）。</li>
</ul>

<h2>5つのステップ</h2>
<ol>
<li><b>試験とスキャン：</b>試験名・スキャン・保存先を決めます。</li>
<li><b>設問の設定：</b>1枚目の答案で、各解答欄を枠で囲みます。</li>
<li><b>氏名の照合：</b>答案と生徒を対応させます。</li>
<li><b>採点：</b>設問ごとに採点します。</li>
<li><b>確認と出力：</b>合計を確認し、生徒レポートとExcelの成績表を作ります。</li>
</ol>

<h2>知っておくと便利なこと</h2>
<ul>
<li>採点はその都度保存されます。続きは<b>「前回の採点を続ける」</b>から始められます。</li>
<li>終了するには、スタート画面の<b>「CAM2を終了」</b>をクリックします。</li>
<li>スキャンの方法は、スタート画面の案内をご覧ください。</li>
<li>スタート画面の上部で、Englishと日本語を切り替えられます。</li>
</ul>
"""


START_STEPS = {
    "windows": (
        """
<li>Unzip the download, open the folder and double-click <b>Start CAM2 Exam Grading</b>.</li>
<li>If Windows says <i>Windows protected your PC</i>, click <b>More info</b>, then <b>Run anyway</b>.</li>
""",
        """
<li>ダウンロードしたzipを展開し、フォルダーを開いて<b>「Start CAM2 Exam Grading」</b>をダブルクリックします。</li>
<li>「WindowsによってPCが保護されました」と表示されたら、<b>「詳細情報」</b>、<b>「実行」</b>の順にクリックします。</li>
"""),
    "mac": (
        """
<li>Double-click the download to unzip it, open the folder and double-click <b>Start CAM2 Exam Grading</b>.</li>
<li>The first time, your Mac stops it because it isn't signed. Click <b>Done</b>, open <b>System Settings &gt; Privacy &amp; Security</b>, scroll down and click <b>Open Anyway</b>, then enter your password. You only do this once.</li>
<li>If your Mac asks whether CAM2 may use a folder such as Documents, click <b>Allow</b>.</li>
""",
        """
<li>ダウンロードしたファイルをダブルクリックして展開し、フォルダーを開いて<b>「Start CAM2 Exam Grading」</b>をダブルクリックします。</li>
<li>初回は、署名がないためMacに止められます。<b>「完了」</b>をクリックし、<b>「システム設定」＞「プライバシーとセキュリティ」</b>を開いて下へスクロールし、<b>「このまま開く」</b>をクリックしてパスワードを入力します。これは最初の1回だけです。</li>
<li>書類フォルダーなどへのアクセスを求められたら、<b>「許可」</b>をクリックします。</li>
"""),
}


def build(output: str, system: str = "windows") -> None:
    doc = fitz.open()
    for body, steps in zip((ENGLISH, JAPANESE), START_STEPS[system]):
        page = doc.new_page(width=595, height=842)
        body = body.replace("{start_steps}", steps)
        spare, _scale = page.insert_htmlbox(fitz.Rect(48, 48, 547, 794), body, css=CSS, scale_low=1)
        assert spare >= 0, "the quick guide no longer fits on its page"
    doc.subset_fonts()
    doc.save(output, garbage=4, deflate=True)
    doc.close()


if __name__ == "__main__":
    build(*sys.argv[1:])
