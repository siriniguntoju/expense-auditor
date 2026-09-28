class AgentFailure(RuntimeError):
    def __init__(self, code):
        self.code = code
        messages = {
            429: "Gemini free-tier quota is exhausted. No retry or paid fallback was used.",
            503: "Gemini is temporarily unavailable. Saved extractions can be reused when you resume.",
            "CACHE_MISSING": "A real Gemini extraction is missing from the cache. Run the extraction benchmark first.",
            "INVALID_INPUT": "The agent could not validate its input or extraction. Review the report and model response schema.",
        }
        self.safe_message = messages.get(
            code, "An agent failed. Check the local services and retry with a new run."
        )
        super().__init__(self.safe_message)
