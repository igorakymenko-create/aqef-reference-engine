"""Local subject and Judge for the GitHub-hosted example."""

from fastapi import FastAPI

app = FastAPI()


@app.post("/subject")
def subject():
    return {"response": "Hello from the example subject"}


@app.post("/judge")
def judge():
    return {"verdict": "pass", "confidence": 1.0,
            "explanation": "The example greeting was returned.", "assertions": 1}
