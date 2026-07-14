from __future__ import annotations

from app.schemas.prompt import PromptGenerateRequest
from app.services.prompt_blocks.composer import PromptComposer
from app.services.prompt_labels import (
    LOCALIZATION_LEVEL_LABELS,
    bool_label,
)


class PromptGenerator:
    def generate(self, data: PromptGenerateRequest) -> str:
        return PromptComposer(data).compose()

    def generate_analysis_prompt(self, data: PromptGenerateRequest) -> str:
        return PromptComposer(data).compose_analysis()

    def generate_final_prompt_from_analysis(self, data: PromptGenerateRequest, analysis_json: dict) -> str:
        return PromptComposer(data).compose_from_analysis(analysis_json)

    def generate_story_plan_from_analysis(self, data: PromptGenerateRequest, analysis_json: dict) -> str:
        return PromptComposer(data).compose_story_plan_from_analysis(analysis_json)

    def generate_final_prompt_from_story_plan(self, data: PromptGenerateRequest, analysis_json: dict, story_plan_json: dict) -> str:
        return PromptComposer(data).compose_from_story_plan(analysis_json, story_plan_json)

    def generate_timeline_scout_prompt(self, data: PromptGenerateRequest) -> str:
        return PromptComposer(data).compose_timeline_scout()

    def generate_chapter_analysis_prompt(self, data: PromptGenerateRequest, timeline_json: dict, chapter: dict) -> str:
        return PromptComposer(data).compose_chapter_analysis(timeline_json, chapter)

    def generate_coverage_review_prompt(self, data: PromptGenerateRequest, timeline_json: dict, chapter_analyses: list[dict]) -> str:
        return PromptComposer(data).compose_coverage_review(timeline_json, chapter_analyses)

    def generate_edit_strategy_prompt(self, data: PromptGenerateRequest, timeline_json: dict, chapter_analyses: list[dict], coverage_review: dict) -> str:
        return PromptComposer(data).compose_edit_strategy(timeline_json, chapter_analyses, coverage_review)

    def generate_story_assembly_prompt(self, data: PromptGenerateRequest, timeline_json: dict, chapter_analyses: list[dict], coverage_review: dict, strategy: dict) -> str:
        return PromptComposer(data).compose_story_assembly(timeline_json, chapter_analyses, coverage_review, strategy)

    def generate_director_plan_prompt(self, data: PromptGenerateRequest, timeline_json: dict, chapter_analyses: list[dict]) -> str:
        return PromptComposer(data).compose_director_plan(timeline_json, chapter_analyses)

    def generate_final_chunk_prompt(self, data: PromptGenerateRequest, chunk_name: str, selected_beats: list[dict], chapter_analyses: list[dict], strategy: dict) -> str:
        return PromptComposer(data).compose_final_chunk(chunk_name, selected_beats, chapter_analyses, strategy)

    def generate_alignment_audit_prompt(self, data: PromptGenerateRequest, final_payload: dict, timeline_json: dict, chapter_analyses: list[dict], strategy: dict, assembly: dict) -> str:
        return PromptComposer(data).compose_alignment_audit(final_payload, timeline_json, chapter_analyses, strategy, assembly)

    def generate_compact_alignment_audit_prompt(self, data: PromptGenerateRequest, final_payload: dict, director_plan: dict) -> str:
        return PromptComposer(data).compose_compact_alignment_audit(final_payload, director_plan)

    def generate_source_access_check_prompt(self, data: PromptGenerateRequest) -> str:
        return PromptComposer(data).compose_source_access_check()

    def generate_repair_chunk_prompt(self, data: PromptGenerateRequest, chunk_name: str, previous_chunk: dict, audit_json: dict, selected_beats: list[dict], chapter_analyses: list[dict], strategy: dict) -> str:
        return PromptComposer(data).compose_repair_chunk(chunk_name, previous_chunk, audit_json, selected_beats, chapter_analyses, strategy)
