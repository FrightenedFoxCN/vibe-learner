"""Public planning proposal samples shared by domain and provider tests."""
from app.models.domain import PersonaProfile
from app.models.planning import LEARNING_PLAN_PROPOSAL_SCHEMA_NAME, LEARNING_PLAN_PROPOSAL_SCHEMA_VERSION


def planning_persona() -> PersonaProfile:
    return PersonaProfile(
        id="persona-1",
        name="Test Mentor",
        source="user",
        summary="A deterministic planning test persona.",
        system_prompt="Help the learner build a grounded plan.",
        available_emotions=["focused"],
        available_actions=["explain"],
        default_speech_style="clear",
    )



def valid_proposal_payload() -> dict:
    return {
        "schema_name": LEARNING_PLAN_PROPOSAL_SCHEMA_NAME,
        "schema_version": LEARNING_PLAN_PROPOSAL_SCHEMA_VERSION,
        "course_title": "离散数学基础",
        "overview": "先建立命题逻辑与集合的知识结构。",
        "today_tasks": ["阅读第一章并整理定义。"],
        "schedule": [
            {
                "unit_id": "unit-1",
                "title": "第一章精读",
                "focus": "理解集合与命题逻辑。",
                "activity_type": "learn",
                "schedule_chapters": [
                    {
                        "title": "1.1 集合",
                        "anchor_page_start": 1,
                        "anchor_page_end": 5,
                        "source_section_ids": ["section-1"],
                        "content_slices": [
                            {
                                "page_start": 1,
                                "page_end": 5,
                                "source_section_ids": ["section-1"],
                            }
                        ],
                    }
                ],
            }
        ],
    }

