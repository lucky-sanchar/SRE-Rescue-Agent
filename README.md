# 🚀 Autonomous SRE Rescue Agent
**🥈 2nd Place at Hackathon**

An Enterprise-Grade, AI-powered Site Reliability Engineering (SRE) agent that automatically detects production crashes, identifies the root cause using LLMs, and triggers a zero-touch Git revert to restore the server.

## 🧠 The Problem
When a production server crashes at 2 AM, manual debugging takes time. Traditional UI-automation bots fail when the frontend layout changes. We needed a bulletproof, self-healing system.

## 💡 The Solution & Architecture
Our agent monitors the production URL (Vercel) and leaps into action upon detecting a `500 Internal Server Error`:
1. **Log Extraction:** Grabs server logs dynamically.
2. **AI Root-Cause Analysis:** Uses Groq (Llama-3) API to pinpoint the culprit commit.
3. **Hybrid Execution Engine:** Falls back to a deterministic Git CLI approach (`git clone`, `git revert`, `git push`) ensuring 100% success even if the GitHub UI changes.
4. **Instant Alerting:** Pings the DevOps team via Slack webhooks with the recovery status.

## 🛠️ Tech Stack
* **Core:** Python
* **AI/LLM:** Groq API (Llama-3/GPT-OSS)
* **Automation:** Playwright (for dynamic UI evaluation via WebCMD adapter)
* **Execution:** Git CLI (`subprocess`), REST APIs

## 🚀 How to Run Locally

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install requests python-dotenv playwright
   playwright install
3. Rename .env.example to .env and add your keys.
4. Run the agent:
    ```bash
    python main_agent.py

