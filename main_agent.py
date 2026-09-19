import os
import time
import subprocess
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# CONFIG — all secrets are loaded from a ".env" file sitting next to this
# script (see the .env.example file / setup instructions). Nothing is
# hardcoded here, and .env should never be committed to git.
# ---------------------------------------------------------------------------
load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")          # a PAT with 'repo' scope
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

GITHUB_OWNER = os.environ.get("GITHUB_OWNER")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
BRANCH = os.environ.get("BRANCH", "main")
LOCAL_REPO_PATH = os.environ.get("LOCAL_REPO_PATH", "./anime_clone")
VERCEL_URL = os.environ.get("VERCEL_URL")

REQUIRED_VARS = {
    "GROQ_API_KEY": GROQ_API_KEY,
    "GITHUB_TOKEN": GITHUB_TOKEN,
    "GITHUB_OWNER": GITHUB_OWNER,
    "GITHUB_REPO": GITHUB_REPO,
    "VERCEL_URL": VERCEL_URL,
}
missing = [k for k, v in REQUIRED_VARS.items() if not v]
if missing:
    raise SystemExit(f"[!] Missing required environment variables: {', '.join(missing)}")


# ---------------------------------------------------------------------------
# 1. AI Integration using Groq API
# ---------------------------------------------------------------------------
def analyze_logs_with_groq(logs_text):
    print("\n[AI AGENT] Connecting to Groq to analyze logs...")

    url = "https://api.groq.com/openai/v1/chat/completions"
    prompt = (
        "You are an SRE assistant. Read the following server output. "
        "If there is an error, state the error and the culprit in one short sentence. "
        "If no error, say 'Server is running fine.'\n\n"
        f"Logs: {logs_text[:1000]}"
    )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"AI Error: Groq API call failed. {e}"


# ---------------------------------------------------------------------------
# 2. Human Approval Function
# ---------------------------------------------------------------------------
def ask_for_human_approval(error_text):
    print("\n[AI AGENT] Analyzing the error logs...")

    ai_summary = analyze_logs_with_groq(error_text)
    print(f"-> AI Conclusion: {ai_summary}")

    if "running fine" in ai_summary.lower():
        print("[*] Server is healthy. No rescue needed.")
        return False

    print("\n[CRITICAL ALERT] Do you want me to automatically revert the code and fix this?")
    choice = input("Press 'Y' for Yes, or 'N' for No: ").strip().upper()

    if choice == "Y":
        print("\n[*] Permission Granted! Initiating Git Revert & Slack Alert...")
        return True
    else:
        print("\n[*] Action Aborted. Human intervened. No changes made.")
        return False


# ---------------------------------------------------------------------------
# 3. Slack Webhook Alert
# ---------------------------------------------------------------------------
def send_slack_alert(commit_sha):
    print("\n[*] Triggering Slack API for Team Notification...")

    message = {
        "text": (
            "🚨 *SRE CRITICAL ALERT* 🚨\n"
            f"Server crashed due to recent commit `{commit_sha}`.\n"
            "✅ *Status:* Agent has successfully reverted the code. Server is recovering."
        )
    }

    if not SLACK_WEBHOOK_URL or "hooks.slack.com" not in SLACK_WEBHOOK_URL:
        print("[*] Slack Alert skipped (SLACK_WEBHOOK_URL not configured).")
        return

    try:
        requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
        print("[*] Slack Alert Sent Successfully! ✅")
    except Exception as e:
        print(f"[!] Slack API failed: {e}")


# ---------------------------------------------------------------------------
# 4. Git-based revert (replaces the old Playwright GitHub-UI automation)
#
# Why: GitHub only shows a "Revert this commit" BUTTON in specific PR /
# merge-commit contexts. A commit pushed directly to main (like your
# a1b2c3d) usually has no such button on its commit page — that's why
# get_by_text("Revert this commit") timed out. Driving the browser to
# find UI elements that may not exist is inherently fragile. Using git
# directly is deterministic and doesn't depend on GitHub's web layout.
# ---------------------------------------------------------------------------
def get_latest_commit_sha():
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/commits/{BRANCH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()["sha"]


def revert_latest_commit():
    print("\n[*] Fetching latest commit via GitHub API...")
    sha = get_latest_commit_sha()
    print(f"[*] Culprit commit: {sha}")

    # Token-authenticated HTTPS remote — no password typed anywhere.
    repo_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_OWNER}/{GITHUB_REPO}.git"

    if not os.path.exists(LOCAL_REPO_PATH):
        print("[*] Cloning repo...")
        subprocess.run(["git", "clone", repo_url, LOCAL_REPO_PATH], check=True)
    else:
        print("[*] Repo already cloned locally, syncing...")
        subprocess.run(["git", "-C", LOCAL_REPO_PATH, "fetch", "origin"], check=True)
        subprocess.run(["git", "-C", LOCAL_REPO_PATH, "checkout", BRANCH], check=True)
        subprocess.run(["git", "-C", LOCAL_REPO_PATH, "reset", "--hard", f"origin/{BRANCH}"], check=True)

    print(f"[*] Reverting commit {sha}...")
    subprocess.run(["git", "-C", LOCAL_REPO_PATH, "revert", "--no-edit", sha], check=True)

    print("[*] Pushing revert to origin/main...")
    subprocess.run(["git", "-C", LOCAL_REPO_PATH, "push", "origin", BRANCH], check=True)

    print("[*] Commit reverted and pushed successfully ✅")
    print("[!] VERCEL: New code has been pushed. Give Vercel ~2 minutes to redeploy before checking the site.")
    return sha


# ---------------------------------------------------------------------------
# 5. Main Agent Function
# ---------------------------------------------------------------------------
def check_server_status():
    print("[*] SRE Agent Started...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        page = browser.new_page(no_viewport=True)

        print(f"[*] Navigating to {VERCEL_URL} ...")
        page.goto(VERCEL_URL)

        page.wait_for_timeout(3000)

        page_text = page.locator("body").inner_text()

        print("\n--- SERVER LOGS FOUND ---")
        print(page_text[:300] + "\n...[truncated for screen]")
        print("-------------------------\n")

        browser.close()

    proceed_to_fix = ask_for_human_approval(page_text)

    if proceed_to_fix:
        commit_sha = revert_latest_commit()
        send_slack_alert(commit_sha)
        print("\n🎉 [SUCCESS] SRE Rescue Agent completed its workflow!")


if __name__ == "__main__":
    check_server_status()