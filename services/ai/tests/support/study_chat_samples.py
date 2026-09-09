from app.models.domain import PersonaProfile


def raw_chat_reply(content: str) -> dict[str, object]:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": content},
            }
        ]
    }


def study_persona() -> PersonaProfile:
    return PersonaProfile(
        id="persona-strict-chat",
        name="Strict Chat Tutor",
        source="test",
        summary="A test persona.",
        system_prompt="",
        available_emotions=["calm"],
        available_actions=["point"],
        default_speech_style="steady",
    )


def question_reply() -> dict[str, object]:
    return {
        "text": "先完成这道题，再告诉我你的思路。",
        "mood": "calm",
        "action": "指向题目",
        "interactive_question": {
            "question_type": "multiple_choice",
            "prompt": "以下哪一项是向量基？",
            "difficulty": "easy",
            "topic": "vector basis",
            "options": [
                {"key": "A", "text": "线性无关且张成整个空间的一组向量"},
                {"key": "B", "text": "所有长度相等的向量"},
            ],
            "call_back": True,
            "answer_key": "A",
            "accepted_answers": ["A"],
            "explanation": "A 同时满足线性无关与张成条件。",
        },
    }
