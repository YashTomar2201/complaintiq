# ComplaintIQ — instructions for Claude

## The user is a fresher learning through this project
- Explain new concepts in simple language with a small example before using them.
- Prefer simple, readable code over clever code. Add short comments explaining *why*.
- Keep on-screen output minimal: only print what the user needs to know.

## After finishing EVERY phase in FDE-Project-Guide-CFPB-Complaint-Intelligence.md, do this before moving on:

### 1. Update the decision log
Append to `docs/decision-log.md` each important choice made in the phase:
Decision · Reason (with numbers if measured) · Alternatives considered · Trade-offs · How to explain it in an interview (1–2 simple sentences).

### 2. Quiz the user (interactive)
- Ask 5 questions, ONE AT A TIME, and wait for the user's answer before continuing:
  - 3 questions from the "Understanding Check" of that phase in the guide
  - 2 project-specific questions about the actual code/choices/numbers from this phase
- After each answer: say what was right, gently correct what was wrong or missing,
  then give the model answer in simple words.
- If the user says "skip" or "I don't know", explain the answer simply with an example.
- At the end, give a score (e.g. 4/5) and list any topic to revisit.

### 3. Save the quiz
Append to `docs/learning-log.md`: phase name, each question, the user's answer,
the model answer, and topics to revisit.

### 4. Then ask: "Ready for the next phase?" — and wait.

## Project notes
- Python venv lives in `.venv` (Python 3.11). Run with `.venv\Scripts\python`.
- Never commit `.env` or `data/`.
- Phase 6 gold labels must be created by the human, never by the AI.
