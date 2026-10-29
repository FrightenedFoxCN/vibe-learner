"""Small deterministic language templates for local mock workflows."""

from __future__ import annotations

import re

# Fixed templates make the offline flow respect the same preference as providers.
# Source titles/quotes are inserted verbatim; these are not textbook translations.
_TEXT = {
    "zh-tw": (
        "學習計畫",
        "閱讀",
        "整理兩條定義或結論。",
        "學習目標",
        "整理概念、例題與疑問",
        "學習",
        "先確認核心概念和成立條件，再用具體例子檢查理解。請用自己的話複述重點。",
        "先確定本輪學習主線，再用簡短問題檢查理解。",
        "保持清楚而穩定的講解節奏。",
    ),
    "zh": (
        "学习计划",
        "阅读",
        "提取两条定义或结论。",
        "学习目标",
        "整理概念、例题与疑问",
        "学习单元",
        "我们先确认核心概念和成立条件，再用一个具体例子检查理解。请用自己的话复述关键点。",
        "先确定本轮学习主线，再用一个小问题检查理解。",
        "保持清晰的讲解节奏。",
    ),
    "en": (
        "Study plan",
        "Read",
        "Identify two definitions or conclusions.",
        "Learning goal",
        "Organize concepts, examples and questions",
        "Study",
        "First identify the core concept and its conditions, then check your understanding with a concrete example. Explain the key point in your own words.",
        "Let us establish a clear learning goal, then check your understanding with a short question.",
        "Keep the explanation clear and steady.",
    ),
    "fr": (
        "Plan d’étude",
        "Lire",
        "Relever deux définitions ou conclusions.",
        "Objectif d’apprentissage",
        "Organiser les concepts, les exemples et les questions",
        "Étudier",
        "Commençons par le concept central et ses conditions, puis vérifions la compréhension avec un exemple concret. Reformulez le point essentiel avec vos propres mots.",
        "Fixons un objectif clair, puis vérifions la compréhension avec une courte question.",
        "Garder un rythme d’explication clair et régulier.",
    ),
    "de": (
        "Lernplan",
        "Lesen",
        "Zwei Definitionen oder Schlussfolgerungen festhalten.",
        "Lernziel",
        "Begriffe, Beispiele und Fragen ordnen",
        "Lernen",
        "Klären wir zuerst den Kernbegriff und seine Voraussetzungen. Prüfen Sie Ihr Verständnis an einem Beispiel und erklären Sie den Kerngedanken mit eigenen Worten.",
        "Legen wir ein klares Lernziel fest und prüfen wir das Verständnis mit einer kurzen Frage.",
        "Klar und in gleichmäßigem Tempo erklären.",
    ),
    "es": (
        "Plan de estudio",
        "Leer",
        "Identificar dos definiciones o conclusiones.",
        "Objetivo de aprendizaje",
        "Organizar conceptos, ejemplos y preguntas",
        "Estudiar",
        "Primero aclaremos el concepto central y sus condiciones. Comprueba tu comprensión con un ejemplo concreto y explica la idea principal con tus propias palabras.",
        "Fijemos un objetivo claro y comprobemos la comprensión con una pregunta breve.",
        "Mantener una explicación clara y constante.",
    ),
    "ja": (
        "学習計画",
        "読む",
        "定義や結論を二つ整理してください。",
        "学習目標",
        "概念・例・疑問を整理する",
        "学習",
        "まず中心となる概念と成立条件を確認しましょう。具体例で理解を確かめ、要点を自分の言葉で説明してください。",
        "今回の学習目標を明確にしてから、短い質問で理解を確かめましょう。",
        "明確で落ち着いた説明を続ける。",
    ),
    "ko": (
        "학습 계획",
        "읽기",
        "정의나 결론 두 가지를 정리하세요.",
        "학습 목표",
        "개념, 예제와 질문 정리",
        "학습",
        "먼저 핵심 개념과 성립 조건을 확인하세요. 구체적인 예로 이해를 점검하고 핵심 내용을 자신의 말로 설명해 보세요.",
        "명확한 학습 목표를 세우고 짧은 질문으로 이해를 확인해 봅시다.",
        "명확하고 차분하게 설명하기.",
    ),
    "pt": (
        "Plano de estudo",
        "Ler",
        "Identificar duas definições ou conclusões.",
        "Objetivo de aprendizagem",
        "Organizar conceitos, exemplos e perguntas",
        "Estudar",
        "Primeiro, esclareça o conceito central e suas condições. Verifique a compreensão com um exemplo concreto e explique a ideia principal com suas próprias palavras.",
        "Vamos definir um objetivo claro e verificar a compreensão com uma pergunta breve.",
        "Manter uma explicação clara e constante.",
    ),
    "it": (
        "Piano di studio",
        "Leggere",
        "Individuare due definizioni o conclusioni.",
        "Obiettivo di apprendimento",
        "Organizzare concetti, esempi e domande",
        "Studiare",
        "Chiarisci prima il concetto centrale e le sue condizioni. Verifica la comprensione con un esempio concreto e spiega il punto chiave con parole tue.",
        "Definiamo un obiettivo chiaro e verifichiamo la comprensione con una breve domanda.",
        "Mantenere una spiegazione chiara e regolare.",
    ),
    "ru": (
        "Учебный план",
        "Прочитать",
        "Выделить два определения или вывода.",
        "Цель обучения",
        "Упорядочить понятия, примеры и вопросы",
        "Изучить",
        "Сначала уточните основное понятие и условия его применения. Проверьте понимание на конкретном примере и объясните главную мысль своими словами.",
        "Определим ясную цель и проверим понимание коротким вопросом.",
        "Объяснять ясно и последовательно.",
    ),
    "ar": (
        "خطة الدراسة",
        "اقرأ",
        "استخرج تعريفين أو استنتاجين.",
        "هدف التعلم",
        "نظّم المفاهيم والأمثلة والأسئلة",
        "ادرس",
        "لنحدد أولاً المفهوم الأساسي وشروطه، ثم نتحقق من الفهم بمثال ملموس. اشرح الفكرة الأساسية بكلماتك الخاصة.",
        "لنحدد هدفاً واضحاً ثم نتحقق من الفهم بسؤال قصير.",
        "حافظ على شرح واضح ومتدرج.",
    ),
}


def mock_language_text(language: str) -> dict[str, str]:
    base = (
        "zh-tw"
        if language.casefold() in {"zh-tw", "zh-hk", "zh-hant"}
        else language.split("-", 1)[0].lower()
    )
    if base not in _TEXT:
        raise RuntimeError("mock_output_language_not_supported")
    return dict(
        zip(
            (
                "plan",
                "read",
                "task",
                "goal",
                "focus",
                "study",
                "chat",
                "prelude",
                "commentary",
            ),
            _TEXT[base],
            strict=True,
        )
    )


def mock_auto_language(*texts: str) -> str:
    text = next((value for value in texts if value.strip()), "")
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\u3400-\u9fff]", text):
        return "zh-CN"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    if re.search(r"[\u0400-\u04ff]", text):
        return "ru"
    if re.search(r"\b(apprendre|étudier|comprendre|bonjour)\b", text, re.IGNORECASE):
        return "fr"
    return "en"


def mock_study_language(session_prompt: str, message: str) -> str | None:
    codes = re.findall(
        r"^Application output language \(output-language-v1\): ([A-Za-z0-9-]+)$",
        session_prompt,
        re.MULTILINE,
    )
    if not codes:
        return None
    return mock_auto_language(message) if codes[-1] == "auto" else codes[-1]
