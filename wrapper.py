import os
import click
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
import json
import subprocess


# Template to convert natural language to git commands
PROMPT_TEMPLATE = """
You are a CLI assistant that translates natural-language Git instructions into exact shell commands.
You must only return a JSON list of git commands, e.g., ["git status"].
Do not include any explanations, markdown, or plain text.

Use safe and common defaults when details are missing.

Examples:
NL: "go back 2 commits"
CMD: ["git revert HEAD~2"]

NL: "create a new branch called feature-x"
CMD: ["git checkout -b feature-x"]

NL: "switch to main"
CMD: ["git checkout main"]

NL: "rename current branch to release-1.2"
CMD: ["git branch -m release-1.2"]

NL: "reset to origin/main"
CMD: ["git reset --hard origin/main"]

NL: "stage and commit with conventional message"
CMD: ["__auto_commit__"]

NL: "{query}"
CMD:
"""

# Template for generating conventional commit messages
CONVENTIONAL_COMMIT_PROMPT = """
You're a helpful assistant that writes Git commit messages using the Conventional Commits specification:
https://www.conventionalcommits.org/

Only return a single-line message in this format:
<type>(<optional scope>): <description>

Use one of: feat, fix, chore, docs, refactor, test, perf, ci, build, style.

Example:
Changes:
- Modified login form to add password strength meter
Commit: feat(auth): add password strength meter to login form

Now write the commit message based on this diff:
{diff}
Commit:
"""

def ask_llm(nl_text: str) -> list[str]:
    prompt = PROMPT_TEMPLATE.format(query=nl_text)
    try:
        response = client.completions.create(model="gpt-4o-mini",
        prompt=prompt,
        max_tokens=150,
        temperature=0,
        stop=["\n"])
        commands = json.loads(response.choices[0].text.strip())
        return commands
    except Exception as e:
        click.secho(f"Error from OpenAI: {e}", fg="red")
        return []

def get_git_diff_summary() -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return "Could not retrieve diff."

def generate_commit_message(diff: str) -> str:
    prompt = CONVENTIONAL_COMMIT_PROMPT.format(diff=diff)
    try:
        response = client.completions.create(model="gpt-4o-mini",
        prompt=prompt,
        max_tokens=60,
        temperature=0.3,
        stop=["\n"])
        return response.choices[0].text.strip()
    except Exception as e:
        click.secho(f"Error generating commit message: {e}", fg="red")
        return "chore: update"

def run_commands(commands: list[str]):
    for cmd in commands:
        if cmd == "__auto_commit__":
            perform_auto_commit()
            continue

        click.secho(f"Running: {cmd}", fg="green")
        try:
            subprocess.run(cmd.split(), check=True)
        except subprocess.CalledProcessError as e:
            click.secho(f"Command failed: {e}", fg="red")

def perform_auto_commit():
    try:
        subprocess.run(["git", "add", "."], check=True)
        diff = get_git_diff_summary()
        if not diff:
            click.secho("No staged changes to commit.", fg="yellow")
            return
        message = generate_commit_message(diff)
        click.echo(f"Generated commit message: {message}")
        subprocess.run(["git", "commit", "-m", message], check=True)
    except subprocess.CalledProcessError as e:
        click.secho(f"Commit failed: {e}", fg="red")

@click.command()
@click.argument("nl_command", nargs=-1)
def main(nl_command):
    """Run Git commands using natural language"""
    if not nl_command:
        click.echo("Please provide a natural language Git command.")
        return

    nl_text = " ".join(nl_command)
    commands = ask_llm(nl_text)

    if not commands:
        click.echo("No command generated.")
        return

    if click.confirm(f"Run these command(s)? {commands}", default=True):
        run_commands(commands)
    else:
        click.echo("Aborted.")

if __name__ == "__main__":
    main()

