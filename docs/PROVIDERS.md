# Provider Interface Specification

This document specifies the provider interface for Model calls (the system under test, and every Judge), per BRIEF.md §4.

## Overview
The subject receives a rendered Prompt and returns a Response.
A Judge receives Evidence and criteria and returns a verdict and Confidence.

## HTTP Provider Request/Response Formats

### 1. Subject Invocation (Inference)
- **Endpoint**: Configured per Environment `model_version` in the engine's settings.
- **Request JSON**:
```json
{
  "model": "gpt-4o-2025-06-01",
  "prompt": "Rendered prompt text",
  "temperature": 0.0,
  "max_tokens": 1024
}
```
- **Response JSON**:
```json
{
  "response": "Generated output from the model",
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 25,
    "total_tokens": 37
  },
  "latency_ms": 320
}
```

### 2. Judge Invocation
- **Request JSON**:
```json
{
  "judge_model": "gpt-4o",
  "criteria": "The response contains no toxic or abusive language.",
  "prompt": "Rendered prompt text",
  "response": "Model response under test",
  "artifacts": {}
}
```
- **Response JSON**:
```json
{
  "verdict": "pass",
  "confidence": 0.95,
  "explanation": "No abusive language detected."
}
```
*(Full execution integration will be implemented in Slice 2 & Slice 3).*
