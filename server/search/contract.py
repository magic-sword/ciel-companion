"""Search API v1 contract; generate the agent JSON schema from this file."""
from datetime import datetime
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator


class Source(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=1500, pattern=r'^https?://[^\s]+$')
    snippet: str = Field(max_length=1200)
    attribution: str = Field(max_length=600)
    license_url: str | None = Field(default=None, max_length=1500)
    history_url: str | None = Field(default=None, max_length=1500)


class SearchReply(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1] = 1
    status: Literal['ok', 'no_results', 'unavailable', 'rate_limited', 'failed']
    coverage: str = Field(min_length=1, max_length=300)
    content_kind: Literal['search_snippets', 'grounded_summary']
    retrieved_at: AwareDatetime
    results: list[Source] = Field(max_length=5)
    summary: str | None = Field(default=None, max_length=4000)
    reason: str | None = Field(default=None, max_length=100)
    retry_after_seconds: int | None = Field(default=None, ge=0)

    @model_validator(mode='after')
    def consistent(self):
        if self.status == 'ok' and not self.results:
            raise ValueError('ok requires sources')
        if self.status != 'ok' and (self.results or self.summary):
            raise ValueError('non-ok must not contain an answer')
        if self.status == 'ok' and self.content_kind == 'grounded_summary':
            citations = re.findall(r'\[(\d+)\]', self.summary or '')
            if not self.summary or not citations or any(not 1 <= int(i) <= len(self.results) for i in citations):
                raise ValueError('generated summary requires numbered source references')
        if self.content_kind == 'search_snippets' and self.summary is not None:
            raise ValueError('snippets do not contain a generated answer')
        return self
