"""Make a made-up exam, whole class, for testing CAM2 by hand and for the guide's
screenshots. All of it is made up.

    python tools/make_sample_exam.py <output folder>

Creates one folder per language, sample-exam-en and sample-exam-ja, each with:
    exam-whole-class.pdf  7 students' papers of 9 pages each, as greyscale scans,
                          each a few millimetres off, with one page upside down
    late-paper.pdf        one more student, who sat the exam late
    class_list.xlsx       the class list (all 8 students)
    rubrics.xlsx          the three criteria to upload (CAM2 ships no rubric text;
                          this wording is our own, written for the sample)
    Test-guide.pdf        what to do, the grades to give, and the results to expect

The paper has one theme, water, and one or two questions of each common type:
multiple choice, labelling a diagram, filling in blanks, true or false, a
calculation, a graph, a source-based question, a design sketch and a choice of
two essays. Section A is Criterion A, B is Criterion B, C is Criterion C; the
essays count towards B and C. QUESTIONS below is the one table the papers, the
expected results, the guide and tests/test_sample_exam.py all read.

The expected results are worked out here with plain arithmetic, not by CAM2's
engine, so comparing them with the app is a real check.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf as fitz  # noqa: E402
from openpyxl import Workbook  # noqa: E402

from engine import i18n, reports  # noqa: E402

MM = 72 / 25.4
PAGE_W, PAGE_H = 210 * MM, 297 * MM
PAGES_PER_STUDENT = 9
DPI = 200
LANGUAGES = ("en", "ja")
NA = None                   # the student left it blank: give *Not answered*

# --- The paper ----------------------------------------------------------------------------
#
# Each question: its section and criteria, how Exam 1 grades it (``marks`` for a
# marks question, else rubric levels with an optional highest level per
# criterion in ``caps``), its marks in Exam 2 (marks on every question), the page
# it starts on and its kind.
QUESTIONS = {
    "Q1": {"section": "A", "criteria": "A", "marks": 5, "exam2": 5, "page": 2, "kind": "choice"},
    "Q2": {"section": "A", "criteria": "A", "marks": 4, "exam2": 4, "page": 2, "kind": "labels"},
    "Q3": {"section": "A", "criteria": "A", "marks": 5, "exam2": 5, "page": 3, "kind": "blanks"},
    "Q4": {"section": "A", "criteria": "A", "marks": 4, "exam2": 4, "page": 3, "kind": "true_false"},
    "Q5": {"section": "A", "criteria": "A", "marks": 6, "exam2": 6, "page": 3, "kind": "calculation"},
    "Q6": {"section": "B", "criteria": "B", "marks": 6, "exam2": 6, "page": 4, "kind": "graph"},
    "Q7": {"section": "B", "criteria": "B", "marks": None, "exam2": 8, "page": 5, "kind": "source"},
    "Q8": {"section": "C", "criteria": "C", "marks": None, "caps": {"C": 4}, "exam2": 4, "page": 6, "kind": "sketch"},
    "Q9": {"section": "C", "criteria": "BC", "marks": None, "caps": {"B": 6, "C": 6}, "exam2": 8, "page": 7, "kind": "essay"},
    "Q10": {"section": "C", "criteria": "BC", "marks": None, "exam2": 8, "page": 8, "kind": "essay"},
}
CHOICE = ("Q9", "Q10")                 # answer one of them
SECTIONS = ("A", "B", "C")
EXAM2_SHARES = (34, 33, 33)            # equal shares of three sections, leftover to the first
EXAM1_SHARES = (50, 50)                # Section C has no marks in Exam 1, so no share

# The grades to give. A rubric question has one level per criterion, in the order
# of its ``criteria``; in Exam 2 the first number is its marks. Students answer one
# of Q9 and Q10: the third answered both and the sixth neither. The last student
# sat the exam late and comes in late-paper.pdf.
GRADES = [
    {"Q1": 5, "Q2": 4, "Q3": 5, "Q4": 4, "Q5": 6, "Q6": 6, "Q7": (7,), "Q8": (4,), "Q9": NA, "Q10": (7, 8)},
    {"Q1": 4, "Q2": 3, "Q3": 4, "Q4": 3, "Q5": 4, "Q6": 4, "Q7": (5,), "Q8": (3,), "Q9": (5, 5), "Q10": NA},
    {"Q1": 5, "Q2": 4, "Q3": 4, "Q4": 4, "Q5": 5, "Q6": 5, "Q7": (6,), "Q8": (4,), "Q9": (6, 6), "Q10": (5, 6)},
    {"Q1": 2, "Q2": 1, "Q3": 2, "Q4": 2, "Q5": 1, "Q6": 2, "Q7": (2,), "Q8": (1,), "Q9": (2, 3), "Q10": NA},
    {"Q1": 3, "Q2": 2, "Q3": 3, "Q4": 3, "Q5": 3, "Q6": 3, "Q7": NA, "Q8": (2,), "Q9": (4, 3), "Q10": NA},
    {"Q1": 4, "Q2": 3, "Q3": 5, "Q4": 4, "Q5": 5, "Q6": 5, "Q7": (4,), "Q8": (3,), "Q9": NA, "Q10": NA},
    {"Q1": 5, "Q2": 3, "Q3": 4, "Q4": 4, "Q5": 6, "Q6": 6, "Q7": (6,), "Q8": (4,), "Q9": NA, "Q10": (6, 7)},
    {"Q1": 4, "Q2": 4, "Q3": 3, "Q4": 2, "Q5": 4, "Q6": 3, "Q7": (5,), "Q8": (2,), "Q9": (5, 4), "Q10": NA},
]
LATE = len(GRADES) - 1                 # index of the student in late-paper.pdf
BOTH_ESSAYS = 2                        # answered Q9 and Q10
EXAM2_PICK = "Q10"                     # in Exam 2 the teacher counts this one for them
UPSIDE_DOWN = (5, 5)                   # (student, page) scanned the wrong way up
OVER_THE_LINE = 0                      # this student's Q5 working runs outside the box
CROSSED_OUT = 4                        # this student crossed out a word in Q3

STUDENTS = {
    "en": [("Clarke", "Emma"), ("Patel", "Liam"), ("Rossi", "Sofia"), ("Kim", "Noah"), ("Haddad", "Ava"),
           ("Novak", "Leo"), ("Santos", "Mia"), ("Farouk", "Omar")],
    "ja": [("田中", "花"), ("佐藤", "健"), ("鈴木", "結衣"), ("伊藤", "芽衣"), ("渡辺", "空"), ("山本", "陸"),
           ("小林", "葵"), ("中村", "蓮")],
}

RUBRICS = {
    "en": [
        ("Criterion A: Knowing and understanding", (
            ("0", "Does not reach the level below."),
            ("1-2", "Recalls a few facts about water, with mistakes."),
            ("3-4", "Recalls facts and uses them in familiar problems."),
            ("5-6", "Explains ideas and uses them in some new problems."),
            ("7-8", "Explains ideas fully and uses them accurately in new problems."))),
        ("Criterion B: Analysing and evaluating", (
            ("0", "Does not reach the level below."),
            ("1-2", "Reads some information from data or a source."),
            ("3-4", "Describes patterns and says whether a source can be trusted."),
            ("5-6", "Explains patterns and judges a source, giving reasons."),
            ("7-8", "Analyses evidence in depth and reaches a well-supported judgement."))),
        ("Criterion C: Communicating", (
            ("0", "Does not reach the level below."),
            ("1-2", "Ideas are hard to follow; few labels or terms."),
            ("3-4", "Ideas are mostly clear; some labels and terms."),
            ("5-6", "Ideas are clear and organised; terms used correctly."),
            ("7-8", "Ideas are clear, well organised and suited to the reader throughout."))),
    ],
    "ja": [
        ("基準A：知識と理解", (
            ("0", "下の段階に達していない。"),
            ("1-2", "水についての事実をいくつか思い出せるが、誤りがある。"),
            ("3-4", "事実を思い出し、なじみのある問題に使える。"),
            ("5-6", "考えを説明し、新しい問題にも一部使える。"),
            ("7-8", "考えを十分に説明し、新しい問題に正確に使える。"))),
        ("基準B：分析と評価", (
            ("0", "下の段階に達していない。"),
            ("1-2", "データや資料から情報を一部読み取れる。"),
            ("3-4", "傾向を説明し、資料が信頼できるかを述べられる。"),
            ("5-6", "傾向の理由を説明し、根拠を示して資料を判断できる。"),
            ("7-8", "根拠を深く分析し、十分に裏づけられた判断ができる。"))),
        ("基準C：コミュニケーション", (
            ("0", "下の段階に達していない。"),
            ("1-2", "考えがわかりにくく、ラベルや用語がほとんどない。"),
            ("3-4", "考えはおおむね明確で、ラベルや用語を一部使っている。"),
            ("5-6", "考えが明確で整理されており、用語を正しく使っている。"),
            ("7-8", "考えが明確でよく整理され、全体を通して読み手に合っている。"))),
    ],
}


def criterion_index(letter: str) -> int:
    return "ABC".index(letter)


def full_name(family: str, given: str, language: str) -> str:
    return f"{family} {given}" if language == "ja" else f"{given} {family}"


def exam2_marks(grade) -> int:
    """The grade on the all-marks paper: a rubric question's first number, 0 for *Not answered*."""
    if grade is NA:
        return 0
    return grade[0] if isinstance(grade, tuple) else grade


def one_decimal(value: Fraction) -> Decimal:
    exact = Decimal(value.numerator) / Decimal(value.denominator)
    return exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def exam1_essay(grades: dict) -> str | None:
    """The essay that counts in Exam 1 ("count the best"): higher sum of levels, Q9 on a tie."""
    answered = [q for q in CHOICE if grades[q] is not NA]
    if not answered:
        return None
    return max(answered, key=lambda q: (sum(grades[q]), -CHOICE.index(q)))


def expected_results(student: int) -> dict:
    """What the guide tells testers to expect, by plain arithmetic.

    Exam 1 is the paper as designed: only Q1 to Q6 have marks (Section A /24,
    Section B /6). Exam 2 has marks on every question (/50), the teacher choosing
    which essay counts for the student who wrote both.
    """
    grades = GRADES[student]
    a = sum(exam2_marks(grades[q]) for q, d in QUESTIONS.items() if d["section"] == "A")
    q6 = exam2_marks(grades["Q6"])
    exam1 = a + q6
    exam1_weighted = Fraction(a, 24) * EXAM1_SHARES[0] + Fraction(q6, 6) * EXAM1_SHARES[1]

    if student == BOTH_ESSAYS:
        essay = exam2_marks(grades[EXAM2_PICK])
    else:
        essay = max(exam2_marks(grades[q]) for q in CHOICE)
    b2 = q6 + exam2_marks(grades["Q7"])
    c2 = exam2_marks(grades["Q8"]) + essay
    exam2 = a + b2 + c2
    exam2_weighted = (Fraction(a, 24) * EXAM2_SHARES[0] + Fraction(b2, 14) * EXAM2_SHARES[1]
                      + Fraction(c2, 12) * EXAM2_SHARES[2])
    return {"exam1_marks": exam1, "exam1_percent": one_decimal(Fraction(exam1 * 100, 30)),
            "exam1_weighted": one_decimal(exam1_weighted), "exam1_essay": exam1_essay(grades),
            "exam2_marks": exam2, "exam2_percent": one_decimal(Fraction(exam2 * 100, 50)),
            "exam2_weighted": one_decimal(exam2_weighted)}


# --- The words on the paper ---------------------------------------------------------------

PAPER = {
    "en": {
        "title": "Grade 8 Interdisciplinary Exam: Water", "name": "Name:", "class": "Class:  8A",
        "minutes": "90 minutes",
        "instructions": "Answer every question in Sections A and B. In Section C, answer Q8 and <b>one</b> of Q9 or Q10. "
                        "Write your answers in the spaces given. Show your working in calculations.",
        "assessed": "How you will be assessed",
        "assessed_lead": "Section A is assessed with Criterion A, Section B with Criterion B, and Section C with "
                         "Criterion C. The essays (Q9, Q10) are also assessed with Criterion B. Q8 is assessed up to "
                         "level 4, Q9 up to level 6, and Q10 up to level 8.",
        "level": "Level",
        "section_a": "Section A: Knowing and understanding (Criterion A)",
        "section_b": "Section B: Analysing and evaluating (Criterion B)",
        "section_c": "Section C: Communicating (Criterion C)",
        "marks": "({n} marks)", "levels": "(levels 0–{n})",
        "q1": "Circle the best answer for each.",
        "q2": "Label the water cycle. Write the correct word in each box A to D.",
        "q2_bank": "Words: evaporation · condensation · precipitation · collection",
        "q3": "Fill in the blanks. Write one word for each gap on the lines below.",
        "q4": "Circle True or False for each statement.",
        "q5": "A school roof is 8 m long and 5 m wide. Each millimetre of rain gives 1 litre of water for every "
              "square metre of roof. (a) How many litres are collected from 12 mm of rain? (b) The school tank "
              "holds 400 litres. Will it overflow? Show your working.",
        "q6": "The table shows the rainfall in a town. Plot the rainfall on the grid and join the points. "
              "Then describe the trend.",
        "q6_month": "Month", "q6_rain": "Rainfall (mm)", "q6_trend": "Trend:",
        "q7": "Read the source, then answer (a), (b) and (c).",
        "q7_source": "<b>Source:</b> from a town newspaper, 2019. “The new dam will end our water worries for ever,” "
                     "said the mayor at the opening. “Our families will never run short again.” The dam was paid for "
                     "by the company that built it, which also sells the water.",
        "q7_parts": ("(a) What is the main claim of the source?",
                     "(b) Use the graph in Q6 to suggest why the town wanted more water storage.",
                     "(c) How far can this source be trusted? Explain your answer."),
        "q8": "Design a label for a refillable water bottle that encourages people to save water. "
              "Sketch the label and annotate your choices.",
        "choose": "Answer ONE of Q9 or Q10. Write the question number you chose in the box.",
        "chose": "I am answering:",
        "q9": "Explain why saving water matters in your community. Use at least two examples.",
        "q10": "Evaluate whether building a dam or saving water at home is the better way for a town to secure its "
               "water. Reach a conclusion.",
        "continued": "{q} continued", "end": "End of the exam",
    },
    "ja": {
        "title": "中学2年 教科横断試験：水", "name": "氏名：", "class": "クラス：2年A組", "minutes": "90分",
        "instructions": "セクションAとBはすべての問いに答えなさい。セクションCは、問8と、問9か問10の<b>どちらか一方</b>に"
                        "答えなさい。解答は決められた場所に書きなさい。計算問題は途中の式も書きなさい。",
        "assessed": "評価のしかた",
        "assessed_lead": "セクションAは基準A、セクションBは基準B、セクションCは基準Cで評価します。論述（問9・問10）は基準Bでも"
                         "評価します。問8はレベル4まで、問9はレベル6まで、問10はレベル8まで評価します。",
        "level": "レベル",
        "section_a": "セクションA：知識と理解（基準A）",
        "section_b": "セクションB：分析と評価（基準B）",
        "section_c": "セクションC：コミュニケーション（基準C）",
        "marks": "（{n}点）", "levels": "（レベル0〜{n}）",
        "q1": "最も適切なものを1つ選び、丸で囲みなさい。",
        "q2": "水の循環の図に名前をつけなさい。A〜Dの枠に正しい語を書きなさい。",
        "q2_bank": "語群：蒸発・凝結・降水・集水",
        "q3": "空欄にあてはまる語を、下の解答らんに1語ずつ書きなさい。",
        "q4": "正しいものには「正」、誤っているものには「誤」を丸で囲みなさい。",
        "q5": "学校の屋根は縦8 m、横5 mである。雨が1 mm降ると、屋根1 m²あたり1リットルの水が集まる。"
              "(a) 12 mmの雨で何リットル集まるか。(b) 学校のタンクは400リットル入る。あふれるか。途中の式も書きなさい。",
        "q6": "表はある町の降水量である。グラフ用紙に点を打って線で結び、変化の傾向を説明しなさい。",
        "q6_month": "月", "q6_rain": "降水量（mm）", "q6_trend": "傾向：",
        "q7": "資料を読み、(a)〜(c)に答えなさい。",
        "q7_source": "<b>資料：</b>2019年の町の新聞より。「新しいダムで、町の水の心配はなくなる」と、町長は完成式で述べた。"
                     "「もう家庭の水が足りなくなることはない」。ダムの費用は建設した会社が出しており、その会社は水の販売も行っている。",
        "q7_parts": ("(a) この資料の主な主張は何か。",
                     "(b) 問6のグラフを使い、町が水をためる施設を求めた理由を考えなさい。",
                     "(c) この資料はどの程度信頼できるか。理由も書きなさい。"),
        "q8": "水の節約をよびかける、くり返し使える水筒のラベルをデザインしなさい。スケッチをかき、工夫した点を書き込みなさい。",
        "choose": "問9か問10のどちらか一方に答えなさい。選んだ問題の番号を枠に書きなさい。",
        "chose": "選んだ問題：",
        "q9": "地域で水を節約することがなぜ大切か、例を2つ以上あげて説明しなさい。",
        "q10": "町の水を確保するには、ダムを造ることと家庭で節水することのどちらがよいか、評価して結論を述べなさい。",
        "continued": "{q}（つづき）", "end": "試験はこれで終わりです",
    },
}

# Q1: (question, options, index of the right answer)
MULTIPLE_CHOICE = {
    "en": [("1.1 About how much of Earth's water is fresh water?", ("3%", "25%", "50%", "97%"), 0),
           ("1.2 At sea level, water boils at:", ("50 °C", "80 °C", "100 °C", "120 °C"), 2),
           ("1.3 Which part of a plant takes in most of its water?", ("leaves", "roots", "flowers", "seeds"), 1),
           ("1.4 Water vapour turning into liquid is called:", ("melting", "freezing", "evaporation", "condensation"), 3),
           ("1.5 Which uses the most water in a typical home?", ("toilet", "kettle", "cooking", "brushing teeth"), 0)],
    "ja": [("1.1 地球の水のうち、淡水はおよそ何％か。", ("3%", "25%", "50%", "97%"), 0),
           ("1.2 海面の高さで水が沸騰する温度は。", ("50 ℃", "80 ℃", "100 ℃", "120 ℃"), 2),
           ("1.3 植物で水を主に吸収する部分は。", ("葉", "根", "花", "種"), 1),
           ("1.4 水蒸気が液体の水になる変化は。", ("融解", "凝固", "蒸発", "凝結"), 3),
           ("1.5 ふつうの家庭で最も多く水を使うのは。", ("トイレ", "やかん", "料理", "歯みがき"), 0)],
}

# Q2: the right word for boxes A to D, then the wrong words a student might write instead.
LABELS = {"en": (("evaporation", "condensation", "precipitation", "collection"), ("melting", "rain", "clouds", "river")),
          "ja": (("蒸発", "凝結", "降水", "集水"), ("融解", "雨", "雲", "川"))}

# Q3: the text with numbered gaps, the right words, and wrong ones.
BLANKS = {
    "en": ("Plants lose water through their leaves by (1) ______. Water that soaks into the ground becomes "
           "(2) ______ water. A (3) ______ is a large store of water behind a dam. Water that is safe to drink is "
           "called (4) ______ water. Reusing water from sinks and showers is called (5) ______ water.",
           ("transpiration", "ground", "reservoir", "drinking", "grey"),
           ("breathing", "rain", "river", "clean", "used")),
    "ja": ("植物は葉から（1）______によって水を出す。地面にしみこんだ水は（2）______水になる。ダムの後ろにたまった大量の水を"
           "（3）______という。安全に飲める水を（4）______水という。台所やシャワーの水を再利用する水を（5）______水という。",
           ("蒸散", "地下", "貯水池", "飲料", "中"),
           ("呼吸", "雨", "川", "きれいな", "使った")),
}

# Q4: (statement, true?)
TRUE_FALSE = {
    "en": [("4.1 Ice floats because it is less dense than liquid water.", True),
           ("4.2 Most of Earth's fresh water is in rivers and lakes.", False),
           ("4.3 Clouds are made of tiny drops of water or ice.", True),
           ("4.4 Salt water can be drunk safely without treatment.", False)],
    "ja": [("4.1 氷は液体の水より密度が小さいので浮く。", True),
           ("4.2 地球の淡水のほとんどは川と湖にある。", False),
           ("4.3 雲は小さな水や氷の粒でできている。", True),
           ("4.4 海水は処理しなくても安全に飲める。", False)],
}
TF_WORDS = {"en": ("True", "False"), "ja": ("正", "誤")}

RAINFALL = (("Jan", "1月", 50), ("Feb", "2月", 40), ("Mar", "3月", 80), ("Apr", "4月", 120), ("May", "5月", 160),
            ("Jun", "6月", 210))

# Answers that are strong, middling and weak, for each written part.
WRITTEN = {
    "en": {
        "Q5": ("(a) Area = 8 × 5 = 40 m². 40 × 12 = 480 litres.\n(b) 480 is more than 400, so yes, the tank "
               "overflows by 80 litres. The school needs a bigger tank or a second one.",
               "(a) 8 × 5 = 40, 40 × 12 = 480 L\n(b) yes it overflows",
               "8 × 12 = 96 litres. No."),
        "Q6": ("Rainfall rises every month after February, from 40 mm to 210 mm in June, and it rises fastest "
               "from May to June.",
               "It gets more rainy towards June.",
               "It rains."),
        "Q7": (("The mayor claims the dam will solve the town's water problems for ever.",
                "Rain falls mostly in a few months (up to 210 mm in June), so the town has to store it for the dry months.",
                "Not fully. The mayor wants the dam to look good, and the company that paid for it profits from "
                "selling the water, so both have reasons to exaggerate."),
               ("The dam will stop water problems.",
                "Because it rains a lot in June.",
                "Not much, because the company sells the water."),
               ("A dam was built.", "More rain.", "It is from a newspaper so it is true.")),
        "Q8": (("big drop = easy to see", "blue and green: water and nature", "slogan: Every drop counts",
                "refill points map on the back"),
               ("drop logo", "blue colour", "slogan"),
               ("water",)),
        "Q9": ("Saving water matters because our town gets most of its rain in only a few months. In winter the "
               "reservoir can fall very low, and two years ago there was a hosepipe ban for six weeks. If every "
               "family used a little less, the water would last until the rainy season.\n"
               "A second reason is the cost. Cleaning and pumping water uses a lot of electricity, so wasting water "
               "also wastes energy and money. Our school fixed its dripping taps last year and the water bill fell.\n"
               "Finally, rivers need water too. When too much is taken, the river near the park becomes shallow and "
               "warm, and fish die. Saving water at home protects the plants and animals that share it with us.\n"
               "Small changes, like shorter showers and turning off the tap while brushing teeth, are easy. Together "
               "they help the whole community and the environment, now and in the future.",
               "Saving water is important because sometimes there is not enough water in summer. Last year there was "
               "a hosepipe ban. Also it costs money to clean water. We can save water by having short showers and "
               "turning off taps. This helps everyone in the town.",
               "Water is important. We should save it. Turn off taps."),
        "Q10": ("A dam and saving water at home both help a town secure its water, but in different ways.\n"
                "A dam stores rain from the wet months for the dry months. The graph in Q6 shows rainfall rising from "
                "40 mm in February to 210 mm in June, so storage clearly matters. A dam can also supply a growing town "
                "for many years. However, it is very expensive, it floods land and homes, and it harms river "
                "wildlife. As the source in Q7 shows, the people who build dams can also exaggerate what they will do.\n"
                "Saving water at home is cheap and starts at once. Fixing leaks, shorter showers and collecting "
                "rainwater from roofs, as in Q5, all reduce demand. Its weakness is that it depends on every family "
                "changing its habits, and it cannot store water for a dry season.\n"
                "Weighing these, saving water at home is the better first step, because it is fast, fair and does "
                "not damage the environment. A dam should only be built if the town still runs short after people "
                "have cut their use. The best plan would use both, but in that order.",
                "A dam can store a lot of water for the dry months, which is good, but it costs a lot and floods land. "
                "Saving water at home is cheaper and everyone can help, like having shorter showers. I think saving "
                "water is better because it is cheaper and better for nature.",
                "A dam is better because it holds more water."),
    },
    "ja": {
        "Q5": ("(a) 面積 = 8 × 5 = 40 m²。40 × 12 = 480リットル。\n(b) 480は400より多いので、80リットルあふれる。"
               "大きいタンクか、もう1つタンクが必要である。",
               "(a) 8 × 5 = 40、40 × 12 = 480 L\n(b) あふれる",
               "8 × 12 = 96リットル。あふれない。"),
        "Q6": ("2月より後は毎月降水量が増え、2月の40 mmから6月の210 mmになる。5月から6月の増え方が最も大きい。",
               "6月に向かって雨が多くなる。",
               "雨がふる。"),
        "Q7": (("町長は、ダムで町の水の問題がずっと解決すると主張している。",
                "雨は一部の月に多く（6月は210 mm）、乾いた月のために水をためる必要があるから。",
                "あまり信頼できない。町長はダムをよく見せたいし、費用を出した会社は水を売ってもうけるので、"
                "どちらも大げさに言う理由がある。"),
               ("ダムで水の問題がなくなる。",
                "6月に雨が多いから。",
                "会社が水を売っているので、あまり信頼できない。"),
               ("ダムができた。", "雨が多い。", "新聞なので正しい。")),
        "Q8": (("大きなしずく＝目立つ", "青と緑：水と自然", "標語：一滴を大切に", "裏に給水所の地図"),
               ("しずくのマーク", "青い色", "標語"),
               ("水",)),
        "Q9": ("水を節約することが大切なのは、わたしたちの町では雨が一年のうち数か月に集中するからである。冬には貯水池の水が"
               "とても少なくなり、2年前には6週間の散水制限があった。どの家庭も少しずつ使う量を減らせば、雨の季節まで水がもつ。\n"
               "二つ目の理由は費用である。水をきれいにして送るには多くの電気が必要なので、水のむだは電気とお金のむだにもなる。"
               "わたしの学校では昨年、水もれしていた蛇口を直し、水道代が下がった。\n"
               "さらに、川にも水が必要である。水を取りすぎると、公園の近くの川が浅く温かくなり、魚が死んでしまう。家庭で節水"
               "することは、水を分け合う動植物を守ることにもなる。\n"
               "シャワーを短くする、歯みがきの間は水を止めるなど、小さな工夫は簡単である。みんなで取り組めば、地域全体と自然を"
               "今も将来も守ることができる。",
               "水の節約が大切なのは、夏に水が足りなくなることがあるからだ。去年は散水制限があった。また水をきれいにするには"
               "お金がかかる。シャワーを短くしたり蛇口を止めたりして節約できる。これは町のみんなのためになる。",
               "水は大切だ。節約しよう。蛇口を止める。"),
        "Q10": ("ダムも家庭での節水も町の水を確保するのに役立つが、そのしかたは異なる。\n"
                "ダムは雨の多い月の水を乾いた月のためにためておける。問6のグラフでは降水量が2月の40 mmから6月の210 mmへと"
                "増えており、水をためることの大切さがわかる。また、人口が増える町にも長く水を送れる。しかし、費用がとても"
                "高く、土地や家を水に沈め、川の生き物にも害がある。問7の資料のように、ダムを造る側が効果を大げさに言うこともある。\n"
                "家庭での節水は安く、すぐに始められる。水もれを直す、シャワーを短くする、問5のように屋根の雨水を集めるなど、"
                "どれも使う量を減らす。弱点は、すべての家庭が習慣を変える必要があり、乾いた季節のために水をためられないことである。\n"
                "これらを比べると、まずは家庭での節水がよい。速く、公平で、自然をこわさないからである。人々が使う量を減らしても"
                "なお足りないときにだけ、ダムを造るべきである。両方を使うのが最もよいが、この順番で行うべきだ。",
                "ダムは乾いた月のために水をたくさんためられるのでよいが、費用が高く土地が沈む。家庭での節水は安く、シャワーを"
                "短くするなどだれでも協力できる。安くて自然にもよいので、節水のほうがよいと思う。",
                "ダムのほうが水をたくさんためられるのでよい。"),
    },
}

WRITING_CSS = {"en": "* { font-family: serif; font-style: italic; color: #1a1a80; font-size: 13pt; line-height: 1.5; }",
               "ja": "* { font-family: sans-serif; color: #1a1a80; font-size: 12pt; line-height: 1.6; }"}
# Bigger than the short answers, as handwriting in an essay usually is, with one
# line of writing to each 9 mm ruled line (25.5 pt).
ESSAY_CSS = {"en": "* { font-family: serif; font-style: italic; color: #1a1a80; font-size: 15pt; line-height: 1.7; }"
                   " p { margin: 0; text-indent: 18pt; }",
             "ja": "* { font-family: sans-serif; color: #1a1a80; font-size: 14pt; line-height: 1.82; }"
                   " p { margin: 0; text-indent: 14pt; }"}
PRINT_CSS = ("* { font-family: sans-serif; color: #111111; font-size: 10.5pt; line-height: 1.3; } b { font-size: 11pt; } "
             "h1 { font-size: 15pt; margin: 0; } h2 { font-size: 12pt; margin: 0; }")
INK = (0.1, 0.1, 0.5)
GREY = (0.45, 0.45, 0.45)
RULE = 9                    # mm between the lines in an essay space


def tier(grade, out_of: int) -> int:
    """0 strong, 1 middling, 2 weak: which written answer a grade gets."""
    score = exam2_marks(grade) / out_of
    return 0 if score >= 0.75 else 1 if score >= 0.4 else 2


def out_of(qid: str) -> int:
    d = QUESTIONS[qid]
    return d["marks"] or min((d.get("caps") or {}).values(), default=8)


# --- Drawing the papers ----------------------------------------------------------------------

class _Paper:
    """One student's paper. Positions are in millimetres from the printed page's
    top left; ``dx, dy`` shift everything a little, as a real scan would."""

    def __init__(self, language: str, rng: random.Random):
        self.language = language
        self.words = PAPER[language]
        self.rng = rng
        self.dx, self.dy = rng.uniform(-3, 3) * MM, rng.uniform(-3, 3) * MM
        self.doc = fitz.open()
        self.page = None

    def new_page(self):
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        return self.page

    def rect(self, x0, y0, x1, y1) -> fitz.Rect:
        return fitz.Rect(x0 * MM + self.dx, y0 * MM + self.dy, x1 * MM + self.dx, y1 * MM + self.dy)

    def point(self, x, y) -> fitz.Point:
        return fitz.Point(x * MM + self.dx, y * MM + self.dy)

    def printed(self, box, html, css=PRINT_CSS):
        spare, _ = self.page.insert_htmlbox(self.rect(*box), html, css=css, scale_low=1)
        assert spare >= 0, f"printed text doesn't fit: {html[:60]}"

    def write(self, box, text, css=None):
        """Handwriting. Text that doesn't fit is a mistake in this script, so fail."""
        if not text:
            return
        html = "<br>".join(_escape(line) for line in text.split("\n"))
        spare, _ = self.page.insert_htmlbox(self.rect(*box), html, css=css or WRITING_CSS[self.language], scale_low=1)
        assert spare >= 0, f"handwriting doesn't fit: {text[:60]}"

    def frame(self, box, width=0.6):
        self.page.draw_rect(self.rect(*box), color=GREY, width=width)

    def line(self, x0, y0, x1, y1, color=INK, width=1.0):
        self.page.draw_line(self.point(x0, y0), self.point(x1, y1), color=color, width=width)

    def heading(self, qid: str, top: float, text: str, height: float = 16):
        d = QUESTIONS[qid]
        tail = self.words["marks"].format(n=d["marks"]) if d["marks"] else \
            self.words["levels"].format(n=out_of(qid))
        self.printed((20, top, 190, top + height), f"<b>{qid[1:]}</b>&nbsp; {text} {tail}")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _split_to_fit(paragraphs, box_mm, css) -> tuple:
    """How many characters of the essay fit in the first space: the rest goes on the next page."""
    text = "\n".join(paragraphs)
    rect = fitz.Rect(0, 0, (box_mm[2] - box_mm[0]) * MM, (box_mm[3] - box_mm[1]) * MM)
    cuts = [m.end() for m in re.finditer(r"[.。]\s?", text)] + [len(text)]

    def fits(n):
        with fitz.open() as scratch:
            page = scratch.new_page(width=rect.width + 10, height=rect.height + 10)
            spare, _ = page.insert_htmlbox(rect, _essay_html(text[:n]), css=css, scale_low=1)
            return spare >= 0

    best = 0
    for n in cuts:
        if not fits(n):
            break
        best = n
    rest = text[best:]
    # a split in the middle of a paragraph carries on without a new indent
    if rest and not text[:best].endswith("\n"):
        rest = "\u2060" + rest.lstrip()
    return text[:best].rstrip(), rest.strip(" ")


def _essay_html(text: str) -> str:
    """Paragraphs, indented; one starting with a word joiner continues the last page's."""
    out = []
    for para in text.split("\n"):
        if not para.strip():
            continue
        style = " style='text-indent:0'" if para.startswith("\u2060") else ""
        out.append(f"<p{style}>{_escape(para.lstrip(chr(0x2060)))}</p>")
    return "".join(out)


def _draw_cover(p: _Paper, name: str):
    w = p.words
    p.new_page()
    p.printed((20, 12, 190, 24), f"<h1>{w['title']}</h1>")
    p.page.draw_rect(p.rect(20, 27, 120, 41), color=(0, 0, 0), width=0.8)
    p.printed((22, 28, 40, 34), w["name"])
    p.write((40, 30, 118, 40), name)
    p.printed((125, 28, 190, 41), f"{w['class']}<br>{w['minutes']}")
    p.printed((20, 47, 190, 70), w["instructions"])
    p.printed((20, 76, 190, 84), f"<h2>{w['assessed']}</h2>")
    p.printed((20, 85, 190, 103), w["assessed_lead"])
    top = 106
    for criterion, bands in RUBRICS[p.language]:
        p.printed((20, top, 190, top + 7), f"<b>{criterion}</b>")
        top += 7
        for levels, descriptor in bands[1:]:
            p.printed((24, top, 44, top + 6), f"{w['level']} {levels.replace('-', '–')}")
            p.printed((46, top, 190, top + 6), descriptor)
            top += 6.2
        top += 4


def _draw_section_a(p: _Paper, grades: dict):
    w, lang = p.words, p.language
    p.new_page()
    p.printed((20, 12, 190, 20), f"<h2>{w['section_a']}</h2>")
    p.heading("Q1", 24, w["q1"], 8)
    items = MULTIPLE_CHOICE[lang]
    order = list(range(len(items)))
    p.rng.shuffle(order)
    right = set(order[:exam2_marks(grades["Q1"])])
    for i, (question, options, key) in enumerate(items):
        top = 34 + i * 18
        p.printed((22, top, 190, top + 7), question)
        chosen = None if grades["Q1"] is NA else key if i in right else (key + 1 + p.rng.randrange(3)) % 4
        for j, option in enumerate(options):
            x = 28 + j * 40
            p.printed((x, top + 8, x + 6, top + 15), "ABCD"[j])
            p.printed((x + 6, top + 8, x + 39, top + 15), option)
            if j == chosen:
                p.page.draw_circle(p.point(x + 1.6, top + 10.2), 3.4 * MM, color=INK, width=1.1)

    p.heading("Q2", 128, w["q2"], 8)
    p.printed((22, 137, 190, 143), w["q2_bank"])
    _draw_water_cycle(p, grades["Q2"])


def _draw_water_cycle(p: _Paper, grade):
    """A simple water-cycle diagram with four label boxes, A to D."""
    page, black = p.page, (0.15, 0.15, 0.15)
    p.frame((20, 146, 190, 282), width=0.4)
    # sea, land and a mountain
    page.draw_polyline([p.point(22, 262), p.point(80, 262)], color=black, width=0.8)
    for x in range(24, 78, 8):
        page.draw_bezier(p.point(x, 266), p.point(x + 2, 264), p.point(x + 4, 268), p.point(x + 6, 266),
                         color=black, width=0.5)
    page.draw_polyline([p.point(80, 262), p.point(120, 232), p.point(150, 205), p.point(188, 262)],
                       color=black, width=0.8)
    # sun, cloud and rain
    page.draw_circle(p.point(40, 172), 9 * MM, color=black, width=0.8)
    for cx, cy, r in ((120, 170, 8), (132, 165, 10), (145, 171, 8)):
        page.draw_circle(p.point(cx, cy), r * MM, color=black, width=0.8, fill=(1, 1, 1))
    for x in (124, 132, 140, 148):
        p.line(x, 184, x - 3, 194, color=black, width=0.6)
    # arrows: up from the sea, across to the cloud, down to the hills, back along a river
    for (x0, y0, x1, y1) in ((55, 255, 75, 200), (85, 180, 108, 170), (160, 196, 160, 214), (150, 250, 92, 258)):
        p.line(x0, y0, x1, y1, color=black, width=0.9)
        page.draw_circle(p.point(x1, y1), 1.1 * MM, color=black, fill=black)
    boxes = ((60, 222), (88, 152), (164, 201), (100, 266))     # A: evaporation, B: condensation, ...
    right_words, wrong_words = LABELS[p.language]
    correct = set(range(exam2_marks(grade)))
    for i, (x, y) in enumerate(boxes):
        p.printed((x - 6, y, x - 1, y + 8), f"<b>{'ABCD'[i]}</b>")
        p.page.draw_rect(p.rect(x, y, x + 34, y + 9), color=black, width=0.6, fill=(1, 1, 1))
        if grade is not NA:
            p.write((x + 1.5, y + 0.5, x + 34, y + 9), right_words[i] if i in correct else wrong_words[i])


def _draw_page_3(p: _Paper, grades: dict, student: int):
    w, lang = p.words, p.language
    p.new_page()
    text, right, wrong = BLANKS[lang]
    p.heading("Q3", 14, w["q3"], 8)
    p.printed((22, 23, 190, 52), text)
    correct = set(range(exam2_marks(grades["Q3"])))
    for i in range(5):
        x, y = (22, 56) if i < 3 else (22, 66)
        x += (i % 3) * 56
        p.printed((x, y, x + 8, y + 7), f"({i + 1})")
        p.line(x + 8, y + 7, x + 52, y + 7, color=GREY, width=0.5)
        if grades["Q3"] is NA:
            continue
        word = right[i] if i in correct else wrong[i]
        if student == CROSSED_OUT and i == 1:
            # wrote the wrong word first, crossed it out, then the right one after it
            p.write((x + 9, y, x + 30, y + 7.5), wrong[i])
            p.line(x + 9, y + 3.6, x + 9 + 3.2 * len(wrong[i]) * (2 if lang == "ja" else 1), y + 3.2, width=1.2)
            p.write((x + 31, y, x + 54, y + 7.5), word)
        else:
            p.write((x + 9, y, x + 54, y + 7.5), word)

    p.heading("Q4", 82, w["q4"], 8)
    picked = set(range(exam2_marks(grades["Q4"])))
    true_word, false_word = TF_WORDS[lang]
    for i, (statement, truth) in enumerate(TRUE_FALSE[lang]):
        top = 92 + i * 10
        p.printed((22, top, 150, top + 8), statement)
        p.printed((156, top, 170, top + 8), true_word)
        p.printed((174, top, 190, top + 8), false_word)
        if grades["Q4"] is not NA:
            says_true = truth if i in picked else not truth
            x = 157.5 if says_true else 175.5
            p.page.draw_oval(p.rect(x - 3, top - 0.8, x + (8 if lang == "en" and not says_true else 6), top + 5.6),
                             color=INK, width=1.1)

    p.heading("Q5", 136, w["q5"], 20)
    p.frame((20, 158, 190, 278))
    if grades["Q5"] is not NA:
        answer = WRITTEN[lang]["Q5"][tier(grades["Q5"], 6)]
        p.write((24, 162, 186, 274), answer)
        if student == OVER_THE_LINE:
            # a last line squeezed in below the box and out into the margin
            p.write((60, 275.5, 200, 286), "Check: 40 m² × 12 mm = 480 L ✓" if lang == "en" else "確認：40 m² × 12 mm = 480 L ✓")


def _draw_section_b(p: _Paper, grades: dict):
    w, lang = p.words, p.language
    p.new_page()
    p.printed((20, 12, 190, 20), f"<h2>{w['section_b']}</h2>")
    p.heading("Q6", 24, w["q6"], 12)
    # the data table
    col = 22
    p.printed((col, 38, col + 30, 45), f"<b>{w['q6_month']}</b>")
    p.printed((col, 45, col + 30, 52), f"<b>{w['q6_rain']}</b>")
    for i, (en, ja, mm) in enumerate(RAINFALL):
        x = col + 32 + i * 22
        p.printed((x, 38, x + 20, 45), en if lang == "en" else ja)
        p.printed((x, 45, x + 20, 52), str(mm))
    p.frame((col, 37, col + 32 + 6 * 22, 52), width=0.4)
    # the grid: 0–250 mm up the side, six months along the bottom
    gx0, gy0, gx1, gy1 = 40, 60, 180, 200
    for i in range(0, 15):
        x = gx0 + i * 10
        p.line(x, gy0, x, gy1, color=(0.75, 0.75, 0.75), width=0.3)
    for i in range(0, 15):
        y = gy0 + i * 10
        p.line(gx0, y, gx1, y, color=(0.75, 0.75, 0.75), width=0.3)
    p.line(gx0, gy0, gx0, gy1, color=(0, 0, 0), width=0.8)
    p.line(gx0, gy1, gx1, gy1, color=(0, 0, 0), width=0.8)
    for mm in range(0, 251, 50):
        y = gy1 - mm * 140 / 250
        p.printed((gx0 - 12, y - 2.5, gx0 - 1, y + 3.5), f"<span style='font-size:8pt'>{mm}</span>")
    for i, (en, ja, _mm) in enumerate(RAINFALL):
        x = gx0 + 10 + i * 22
        p.printed((x - 6, gy1 + 1, x + 8, gy1 + 7), f"<span style='font-size:8pt'>{en if lang == 'en' else ja}</span>")
    p.printed((20, gy0 - 6, 70, gy0), f"<span style='font-size:8pt'>{w['q6_rain']}</span>")
    if grades["Q6"] is not NA:
        level = tier(grades["Q6"], 6)
        wrong = {0: set(), 1: {2}, 2: {1, 3, 4}}[level]
        points = []
        for i, (_en, _ja, mm) in enumerate(RAINFALL):
            x = gx0 + 10 + i * 22
            value = mm + (30 if i in wrong else 0)
            y = gy1 - value * 140 / 250
            points.append((x, y))
            p.line(x - 1.5, y - 1.5, x + 1.5, y + 1.5)
            p.line(x - 1.5, y + 1.5, x + 1.5, y - 1.5)
        if level < 2:
            for (x0, y0), (x1, y1) in zip(points, points[1:]):
                p.line(x0, y0, x1, y1, width=0.8)
    p.printed((20, 212, 40, 220), w["q6_trend"])
    p.frame((20, 220, 190, 270))
    if grades["Q6"] is not NA:
        p.write((24, 223, 186, 268), WRITTEN[lang]["Q6"][tier(grades["Q6"], 6)])


def _draw_source(p: _Paper, grades: dict):
    w, lang = p.words, p.language
    p.new_page()
    p.heading("Q7", 14, w["q7"], 8)
    p.page.draw_rect(p.rect(20, 24, 190, 66), color=(0, 0, 0), width=0.8, fill=(0.95, 0.95, 0.95))
    p.printed((25, 28, 185, 63), w["q7_source"])
    answers = None if grades["Q7"] is NA else WRITTEN[lang]["Q7"][tier(grades["Q7"], 8)]
    for i, (question, top) in enumerate(zip(w["q7_parts"], (74, 142, 210))):
        p.printed((20, top, 190, top + 8), question)
        p.frame((20, top + 9, 190, top + 62))
        if answers:
            p.write((24, top + 12, 186, top + 60), answers[i])


def _draw_sketch(p: _Paper, grades: dict):
    w, lang = p.words, p.language
    p.new_page()
    p.printed((20, 12, 190, 20), f"<h2>{w['section_c']}</h2>")
    p.heading("Q8", 24, w["q8"], 14)
    p.frame((20, 40, 190, 230))
    if grades["Q8"] is not NA:
        level = tier(grades["Q8"], 4)
        # the bottle
        page = p.page
        page.draw_polyline([p.point(92, 62), p.point(92, 72), p.point(82, 84), p.point(82, 212),
                            p.point(128, 212), p.point(128, 84), p.point(118, 72), p.point(118, 62),
                            p.point(92, 62)], color=INK, width=1.2)
        page.draw_rect(p.rect(90, 54, 120, 62), color=INK, width=1.2)
        # the label, with a drop on it
        page.draw_rect(p.rect(84, 112, 126, 176), color=INK, width=1.0)
        if level < 2:
            page.draw_bezier(p.point(105, 120), p.point(96, 136), p.point(96, 150), p.point(105, 152),
                             color=INK, width=1.0)
            page.draw_bezier(p.point(105, 120), p.point(114, 136), p.point(114, 150), p.point(105, 152),
                             color=INK, width=1.0)
            p.write((88, 158, 124, 172), "Every drop counts" if lang == "en" else "一滴を大切に",
                    css=WRITING_CSS[lang].replace("13pt", "9pt").replace("12pt", "8pt"))
        notes = WRITTEN[lang]["Q8"][level]
        spots = ((140, 120, 108, 132), (140, 150, 120, 140), (24, 165, 92, 165), (24, 192, 84, 192))
        for note, (x, y, tx, ty) in zip(notes, spots):
            left = x < 100
            p.write((x, y - 5, x + 50, y + 16) if not left else (x, y - 5, x + 56, y + 16), note)
            p.line(x + (56 if left else -1), y, tx, ty, width=0.7)

    p.printed((20, 240, 190, 258), f"<b>{w['choose']}</b>")


def _draw_essays(p: _Paper, grades: dict):
    """Q9 on page 7, running onto page 8; Q10 halfway down page 8, running onto page 9."""
    w, lang = p.words, p.language
    css = ESSAY_CSS[lang]
    spaces = {"Q9": ((20, 44, 190, 284), (20, 22, 190, 140)),
              "Q10": ((20, 186, 190, 284), (20, 22, 190, 170))}

    def ruled(box):
        p.frame(box)
        y = box[1] + RULE
        while y < box[3] - 1:
            p.line(box[0] + 3, y, box[2] - 3, y, color=(0.8, 0.8, 0.8), width=0.3)
            y += RULE

    def essay(qid, first, second_page_box):
        grade = grades[qid]
        if grade is NA:
            return None
        paragraphs = WRITTEN[lang][qid][tier(grade, out_of(qid))].split("\n")
        inner = (first[0] + 4, first[1] + 1.6, first[2] - 4, first[3] - 1)
        now, later = _split_to_fit(paragraphs, inner, css)
        p.page.insert_htmlbox(p.rect(*inner), _essay_html(now), css=css, scale_low=1)
        return later

    def chose_box(top, qid):
        p.printed((120, top, 160, top + 7), w["chose"])
        p.page.draw_rect(p.rect(160, top - 1, 176, top + 7), color=(0, 0, 0), width=0.7)
        if grades[qid] is not NA:
            p.write((163, top - 0.5, 176, top + 7), qid[1:])

    # page 7
    p.new_page()
    p.heading("Q9", 14, w["q9"], 14)
    chose_box(32, "Q9")
    ruled(spaces["Q9"][0])
    rest_q9 = essay("Q9", spaces["Q9"][0], spaces["Q9"][1])

    # page 8
    p.new_page()
    p.printed((20, 14, 190, 21), f"<b>{w['continued'].format(q=w_q(lang, 'Q9'))}</b>")
    ruled(spaces["Q9"][1])
    if rest_q9:
        box = spaces["Q9"][1]
        spare, _ = p.page.insert_htmlbox(p.rect(box[0] + 4, box[1] + 1.6, box[2] - 4, box[3] - 1),
                                         _essay_html(rest_q9), css=css, scale_low=1)
        assert spare >= 0, "the Q9 essay runs past its space"
    p.heading("Q10", 150, w["q10"], 18)
    chose_box(174, "Q10")
    ruled(spaces["Q10"][0])
    rest_q10 = essay("Q10", spaces["Q10"][0], spaces["Q10"][1])

    # page 9
    p.new_page()
    p.printed((20, 14, 190, 21), f"<b>{w['continued'].format(q=w_q(lang, 'Q10'))}</b>")
    ruled(spaces["Q10"][1])
    if rest_q10:
        box = spaces["Q10"][1]
        spare, _ = p.page.insert_htmlbox(p.rect(box[0] + 4, box[1] + 1.6, box[2] - 4, box[3] - 1),
                                         _essay_html(rest_q10), css=css, scale_low=1)
        assert spare >= 0, "the Q10 essay runs past its space"
    p.printed((20, 268, 190, 280), f"<div style='text-align:center'>{w['end']}</div>")


def w_q(language: str, qid: str) -> str:
    return f"問{qid[1:]}" if language == "ja" else qid


def draw_paper(language: str, student: int, rng: random.Random) -> fitz.Document:
    family, given = STUDENTS[language][student]
    grades = GRADES[student]
    p = _Paper(language, rng)
    _draw_cover(p, full_name(family, given, language))
    _draw_section_a(p, grades)
    _draw_page_3(p, grades, student)
    _draw_section_b(p, grades)
    _draw_source(p, grades)
    _draw_sketch(p, grades)
    _draw_essays(p, grades)
    assert len(p.doc) == PAGES_PER_STUDENT
    return p.doc


def _scan(students, language: str, path: str, rng: random.Random) -> None:
    """Papers as one PDF of greyscale page images, as from a photocopier."""
    with fitz.open() as scan:
        for student in students:
            with draw_paper(language, student, rng) as paper:
                for number, page in enumerate(paper, 1):
                    pix = page.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY)
                    image = pix.tobytes("jpeg", jpg_quality=70)
                    upside_down = (student, number) == UPSIDE_DOWN
                    scan.new_page(width=PAGE_W, height=PAGE_H).insert_image(
                        fitz.Rect(0, 0, PAGE_W, PAGE_H), stream=image, rotate=180 if upside_down else 0)
        scan.save(path, garbage=4, deflate=True)


def make_papers(language: str, path: str, late_path: str) -> None:
    rng = random.Random(8)
    _scan([s for s in range(len(GRADES)) if s != LATE], language, path, rng)
    _scan([LATE], language, late_path, rng)


def make_class_list(language: str, path: str) -> None:
    wb = Workbook()
    wb.active.append(["番号", "姓", "名"] if language == "ja" else ["No.", "Family name", "Given name"])
    for i, (family, given) in enumerate(STUDENTS[language], 1):
        wb.active.append([i, family, given])
    wb.save(path)


def make_rubrics(language: str, path: str) -> None:
    wb = Workbook()
    wb.active.append(["基準", "レベル", "記述"] if language == "ja" else ["Criterion", "Levels", "Descriptor"])
    for name, bands in RUBRICS[language]:
        for levels, descriptor in bands:
            wb.active.append([name, levels, descriptor])
    wb.save(path)


# --- The guide -----------------------------------------------------------------------------

UI_WORDS = ("step1.combined", "step1.add_papers", "pages.tools", "pages.turn", "step2.mode.marks", "step2.mode.rubric",
            "step2.boxes.add_criteria", "step2.rubric.upload", "step2.sections.start_short", "step2.sub.choice",
            "step2.choice.pick_teacher", "step5.option.overall_criteria", "step5.option.section_results",
            "step5.option.images_for", "step5.weighting", "step5.preview", "step5.make_all", "grade.not_answered",
            "step4.class_grid")


def _ui(language: str) -> dict:
    """The app's own labels, so the guide quotes exactly what testers see."""
    return {key.replace(".", "_"): i18n.t(key, language).replace("→", "").replace("✂", "").replace("👁", "")
            .replace("📄", "").strip().lstrip("＋+ ") for key in UI_WORDS}


def _crit(language: str, letter: str) -> str:
    return RUBRICS[language][criterion_index(letter)][0]


def _guide_text(language: str) -> dict:
    names = [full_name(f, g, language) for f, g in STUDENTS[language]]
    both, late, flipped = names[BOTH_ESSAYS], names[LATE], names[UPSIDE_DOWN[0]]
    a, b, c = (_crit(language, x) for x in "ABC")
    if language == "ja":
        return {
            "title": "CAM2 テストの手順",
            "lead": "「水」をテーマにした架空の教科横断試験と、架空の生徒8人の答案です。試験を2回つくり、CAM2の主な使い方を試します。"
                    "所要時間はそれぞれ約20分です。採点を考える必要はありません。下の表のとおりに入力して、結果を比べてください。",
            "files": "<b>ファイル：</b> exam-whole-class.pdf（7人分、1人9ページ）、late-paper.pdf（遅れて受けた1人）、"
                     "class_list.xlsx（名簿8人）、rubrics.xlsx（基準3つ）。",
            "start": "どちらの試験も同じように始めます",
            "s": [f"新しいセッションで「{{step1_combined}}」を選び、exam-whole-class.pdf を指定します。1人のページ数は 9 です。",
                  f"答案の確認で、6人目の答案の5ページ目が上下逆です。その答案を開いて5ページ目を表示し、「{{pages_tools}}」の「{{pages_turn}}」を2回押します（1回で90度回ります）。",
                  f"「{{step1_add_papers}}」で late-paper.pdf を追加します。<b>確認：</b>答案が8人分になること。",
                  "枠：氏名欄は1ページ目。問1・問2は2ページ目、問3〜問5は3ページ目、問6は4ページ目、問7は5ページ目"
                  "（資料を囲んでから「＋別の枠を追加」で解答らんを追加）、問8は6ページ目。問9は7ページ目と8ページ目上半分、"
                  "問10は8ページ目下半分と9ページ目の、それぞれ2つの枠です。",
                  "氏名の照合では class_list.xlsx を使います。"],
            "exam1": "試験1：設計どおり（点数とルーブリックの混在、上限レベル、セクション）",
            "e1": [f"はじめ方で「{{step2_mode_rubric}}」を選び、「{{step2_rubric_upload}}」で rubrics.xlsx を読み込みます。",
                   f"基準のチェック：問1〜問5は{a}、問6・問7は{b}、問8は{c}、問9・問10は{b}と{c}。",
                   "切り取りの表で配点を入力します：問1 5点、問2 4点、問3 5点、問4 4点、問5 6点、問6 6点。"
                   f"問6と問8の行で「{{step2_sections_start_short}}」を押します。",
                   f"上限レベル：セクションCの一括設定で{b}と{c}を6までにし、そのあと問8の{c}を4まで、問10の両方を「すべてのレベル」に戻します。",
                   f"「{{step2_sub_choice}}」で問9と問10を「1問に解答」、「得点の高い1問を集計」にします。",
                   "表のとおりに採点します。<b>確認：</b>問1〜問6は点数のボタン、問7〜問10はレベルのボタンが出ること。"
                   "問9・問10は基準ごとにタブがあること。問9は6より上、問8は4より上のレベルが選べないこと。",
                   f"<b>確認：</b>{both}は問9が集計され、問10は集計されないこと（得点の高い方）。",
                   f"確認と出力で「{{step5_weighting}}」にチェックを入れます。<b>確認：</b>セクションAとBが50%ずつになり、"
                   "点数のないセクションCには比重がないこと。割合が下の「試験1 比重あり」と同じになること。",
                   f"「{{step5_option_overall_criteria}}」にチェックを入れ、1人だけ最終レベルを入力して「{{step5_preview}}」を押します。"
                   f"「{{step5_make_all}}」を押します。",
                   "<b>確認：</b>入力したレベルの帯に色がつくこと。空欄の生徒について警告が出ること。レポートに B7、C8 のように出ること。"],
            "exam2": "試験2：すべて点数 → あとから基準とセクションを追加",
            "e2": [f"はじめ方で「{{step2_mode_marks}}」を選びます。配点：問1 5、問2 4、問3 5、問4 4、問5 6、問6 6、問7 8、"
                   "問8 4、問9 8、問10 8。",
                   f"「{{step2_sub_choice}}」で問9と問10を「1問に解答」、「{{step2_choice_pick_teacher}}」にします。",
                   "<b>確認：</b>ルーブリックの画面に一度も案内されないこと。採点は表の最初の数字（例：「5/6」は5点）を使います。",
                   f"確認と出力で、{both}は問9・問10のどちらを集計するか選ぶよう求められます。問10を選びます。"
                   "<b>確認：</b>合計が下の「試験2 合計」と同じになること。",
                   f"設問の設定に戻り、「{{step2_boxes_add_criteria}}」から rubrics.xlsx をアップロードします。問1〜問5に{a}、"
                   f"問6・問7に{b}、問8〜問10に{c}のチェックを入れ、問6と問8の行で「{{step2_sections_start_short}}」を押します。",
                   "<b>確認：</b>切り取り直しが不要で、採点が残っていること。",
                   f"確認と出力で「{{step5_weighting}}」にチェックを入れます。比重は 34・33・33 になります。"
                   "<b>確認：</b>割合が下の「試験2 比重あり」と同じになること。比重を1つ入力しても合計が100%のままであること。",
                   f"「{{step5_option_images_for}}」で1つのセクションのチェックを外し、「{{step5_preview}}」を押します。"
                   "<b>確認：</b>画像を外したセクションが一覧になること。"],
            "grades": "つける採点", "student": "生徒",
            "dash": f"「—」は「{{grade_not_answered}}」を押します。「5/6」は試験1では基準B 5・基準C 6、試験2では5点です。"
                    f"問7と問8の数字は、試験1ではレベル、試験2では点数です。{late}は late-paper.pdf の生徒、{flipped}は5ページ目が上下逆の生徒です。",
            "expect": "期待される結果", "e1_marks": "試験1 点数（/30）", "e1_weighted": "試験1 比重あり",
            "e2_marks": "試験2 合計（/50）", "e2_weighted": "試験2 比重あり",
            "report": "おかしな点があれば、どの手順で何が起きたかをメモして知らせてください。名前や答案は架空のものなので、共有しても問題ありません。",
        }
    return {
        "title": "CAM2 test guide",
        "lead": "A made-up interdisciplinary exam on water and 8 made-up students' papers. You set up two exams, which "
                "between them try the main ways of using CAM2, in about 20 minutes each. You don't have to decide any "
                "grades: give the ones in the table below, then compare your results.",
        "files": "<b>Files:</b> exam-whole-class.pdf (7 students, 9 pages each), late-paper.pdf (one student who sat "
                 "it late), class_list.xlsx (8 names), rubrics.xlsx (three criteria).",
        "start": "Start both exams the same way",
        "s": ["Start a new session, choose “{step1_combined}” and pick exam-whole-class.pdf. Each paper has 9 pages.",
              "On the scan check, the sixth paper has page 5 upside down. Open it, go to page 5 and press "
              "“{pages_turn}” under “{pages_tools}” twice (each press is a quarter turn).",
              "Use “{step1_add_papers}” to add late-paper.pdf. <b>Check:</b> there are now 8 papers.",
              "Boxes: the name box is on page 1. Q1 and Q2 are on page 2, Q3 to Q5 on page 3, Q6 on page 4, Q7 on page 5 "
              "(box the source, then use + Add another box for the answers), Q8 on page 6. Q9 has two boxes, page 7 "
              "and the top half of page 8; Q10 has two, the bottom half of page 8 and page 9.",
              "Use class_list.xlsx when matching names."],
        "exam1": "Exam 1: as designed (marks and rubric levels, highest levels, sections)",
        "e1": ["On the first screen choose “{step2_mode_rubric}”, and use “{step2_rubric_upload}” to load rubrics.xlsx.",
               f"Tick the criteria: Q1 to Q5 {a}, Q6 and Q7 {b}, Q8 {c}, Q9 and Q10 {b} and {c}.",
               "In the Slice screen's table, type marks: Q1 5, Q2 4, Q3 5, Q4 4, Q5 6, Q6 6. Press "
               "“{step2_sections_start_short}” on the Q6 and Q8 rows.",
               f"Highest levels: use Section C's shortcut to set {b} and {c} up to 6. Then set Q8's {c} up to 4, and "
               "put both of Q10's back to all levels.",
               "In “{step2_sub_choice}”, make Q9 and Q10 “answer 1”, counting the best.",
               "Grade as in the table. <b>Check:</b> Q1 to Q6 show mark buttons and Q7 to Q10 show levels. Q9 and Q10 "
               "have a tab for each criterion. Q9 offers no level above 6, and Q8 none above 4.",
               f"<b>Check:</b> for {both}, Q9 counts and Q10 doesn't, because Q9 has the higher levels.",
               "In Review & export, tick “{step5_weighting}”. <b>Check:</b> Sections A and B get 50% each, and "
               "Section C, which has no marks, gets no share. The percentages match “Exam 1 weighted” below.",
               "Tick “{step5_option_overall_criteria}”, type a final level for one student only, and press "
               "“{step5_preview}”. Then press “{step5_make_all}”.",
               "<b>Check:</b> the band of that final level is shaded. You are warned about the blank final levels. "
               "The report shows grades like B7 and C8."],
        "exam2": "Exam 2: marks on every question, then add criteria and sections later",
        "e2": ["On the first screen choose “{step2_mode_marks}”. Marks: Q1 5, Q2 4, Q3 5, Q4 4, Q5 6, Q6 6, Q7 8, "
               "Q8 4, Q9 8, Q10 8.",
               "In “{step2_sub_choice}”, make Q9 and Q10 “answer 1” with “{step2_choice_pick_teacher}”.",
               "<b>Check:</b> you are never sent to a rubric screen. Grade with the first number in the table "
               "(“5/6” is 5 marks).",
               f"In Review & export, CAM2 asks you to choose whether Q9 or Q10 counts for {both}. Choose Q10. "
               "<b>Check:</b> the totals match “Exam 2 total” below.",
               "Go back to Set up questions. Use “{step2_boxes_add_criteria}” to upload rubrics.xlsx. Tick "
               f"{a} on Q1 to Q5, {b} on Q6 and Q7, and {c} on Q8 to Q10. Press “{{step2_sections_start_short}}” on "
               "the Q6 and Q8 rows.",
               "<b>Check:</b> nothing needs slicing again, and every grade is still there.",
               "In Review & export, tick “{step5_weighting}”. The shares are 34, 33 and 33. <b>Check:</b> the "
               "percentages match “Exam 2 weighted” below. Typing one share keeps the total at 100%.",
               "Untick one section under “{step5_option_images_for}”, and press “{step5_preview}”. <b>Check:</b> "
               "that section prints as a grid."],
        "grades": "The grades to give", "student": "Student",
        "dash": "“—” means press “{grade_not_answered}”. “5/6” is Criterion B 5 and Criterion C 6 in Exam 1, and 5 "
                f"marks in Exam 2. Q7 and Q8 are levels in Exam 1 and marks in Exam 2. {late} is in late-paper.pdf; "
                f"{flipped}'s page 5 is upside down.",
        "expect": "The results to expect", "e1_marks": "Exam 1 marks (/30)", "e1_weighted": "Exam 1 weighted",
        "e2_marks": "Exam 2 total (/50)", "e2_weighted": "Exam 2 weighted",
        "report": "If anything looks wrong, note which step and what happened. The names and papers are all made up, so "
                  "they are safe to share.",
    }


def _shown(grade) -> str:
    if grade is NA:
        return "—"
    if isinstance(grade, tuple):
        return "/".join(str(n) for n in grade)
    return str(grade)


def make_guide(language: str, path: str) -> None:
    words = _guide_text(language)
    fill = _ui(language)
    names = [full_name(family, given, language) for family, given in STUDENTS[language]]
    questions = list(QUESTIONS)
    with fitz.open() as doc:
        w = reports._Writer(doc, words["title"])
        w.html(f"<h1>{words['title']}</h1>", gap=6)
        w.html(f"<p>{words['lead']}</p>", gap=4)
        w.html(f"<p>{words['files']}</p>", gap=8)
        w.html(f"<h2>{words['start']}</h2>", gap=3)
        for step in words["s"]:
            w.html(f"<p>{step.format(**fill)}</p>", gap=2)
        w.y += 6
        for title, steps in ((words["exam1"], words["e1"]), (words["exam2"], words["e2"])):
            w.ensure(80)
            w.html(f"<h2>{title}</h2>", gap=3)
            for step in steps:
                w.html(f"<p>{step.format(**fill)}</p>", gap=2)
            w.y += 6
        w.ensure(170)
        w.html(f"<h2>{words['grades']}</h2>", gap=3)
        widths = [reports.CONTENT_W - 10 * 34] + [34] * 10
        head = [f"<p><b>{words['student']}</b></p>"] + [f"<p><b>{w_q(language, q)}</b></p>" for q in questions]
        rows = [head] + [[f"<p>{name}</p>"] + [f"<p>{_shown(GRADES[i][q])}</p>" for q in questions]
                         for i, name in enumerate(names)]
        reports._table(w, widths, rows, [reports.HEADING] + [None] * len(names))
        w.y += 4
        w.html(f"<p class='muted'>{words['dash'].format(**fill)}</p>", gap=8)
        w.ensure(150)
        w.html(f"<h2>{words['expect']}</h2>", gap=3)
        rows = [[f"<p><b>{words[k]}</b></p>" for k in ("student", "e1_marks", "e1_weighted", "e2_marks", "e2_weighted")]]
        for i, name in enumerate(names):
            r = expected_results(i)
            rows.append([f"<p>{name}</p>", f"<p>{r['exam1_marks']} · {r['exam1_percent']}%</p>",
                         f"<p>{r['exam1_weighted']}%</p>", f"<p>{r['exam2_marks']} · {r['exam2_percent']}%</p>",
                         f"<p>{r['exam2_weighted']}%</p>"])
        reports._table(w, [reports.CONTENT_W - 4 * 92] + [92] * 4, rows, [reports.HEADING] + [None] * len(names))
        w.y += 8
        w.html(f"<p>{words['report']}</p>")
        w.finish()
        doc.subset_fonts()
        doc.save(path, garbage=4, deflate=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    args = parser.parse_args(argv)
    for language in LANGUAGES:
        folder = os.path.join(args.out, f"sample-exam-{language}")
        os.makedirs(folder, exist_ok=True)
        make_papers(language, os.path.join(folder, "exam-whole-class.pdf"), os.path.join(folder, "late-paper.pdf"))
        make_class_list(language, os.path.join(folder, "class_list.xlsx"))
        make_rubrics(language, os.path.join(folder, "rubrics.xlsx"))
        make_guide(language, os.path.join(folder, "Test-guide.pdf"))
        print(f"Made {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
