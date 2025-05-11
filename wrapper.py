import os
import click
import json
import logging
import subprocess
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('git-ai')

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Template to convert natural language to git commands
PROMPT_TEMPLATE = """
You are a CLI assistant that translates natural-language Git instructions into exact shell commands.
You must only return a JSON list of git commands, e.g., ["git status"].
Do not include any explanations, markdown, or plain text.

Use safe and common defaults when details are missing.

When the user mentions "commit" or asks to "save changes" in any way, always use the special "__auto_commit__" command to ensure proper conventional commit messages are generated.

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

NL: "commit my changes"
CMD: ["__auto_commit__"]

NL: "save my work"
CMD: ["__auto_commit__"]

NL: "commit the changes I made to the login page"
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
    logger.info(f"Sending prompt to LLM: '{nl_text}'")
    try:
        response = client.completions.create(model="gpt-4o-mini",
        prompt=prompt,
        max_tokens=150,
        temperature=0,
        stop=["\n"])
        commands = json.loads(response.choices[0].text.strip())
        logger.info(f"LLM generated commands: {commands}")
        return commands
    except Exception as e:
        error_msg = f"Error from OpenAI: {e}"
        logger.error(error_msg)
        click.secho(error_msg, fg="red")
        return []

def get_git_diff_summary() -> str:
    logger.info("Retrieving git diff summary for staged changes")
    try:
        # Get file status (added, modified, deleted)
        status_result = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            capture_output=True,
            text=True,
            check=True
        )

        # Get actual content diff for better context
        diff_result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True,
            text=True,
            check=True
        )

        # Combine both for better context
        combined_diff = f"Files changed:\n{status_result.stdout.strip()}\n\nDetails:\n{diff_result.stdout.strip()}"
        logger.info(f"Retrieved diff summary: {len(combined_diff)} characters")
        return combined_diff
    except subprocess.CalledProcessError as e:
        error_msg = f"Could not retrieve diff: {e}"
        logger.error(error_msg)
        return error_msg

def generate_commit_message(diff: str) -> str:
    logger.info("Generating conventional commit message based on diff")

    if not diff or diff.startswith("Could not retrieve diff"):
        logger.warning("No meaningful diff available for commit message generation")
        return "chore: update files"

    prompt = CONVENTIONAL_COMMIT_PROMPT.format(diff=diff)
    try:
        response = client.completions.create(model="gpt-4o-mini",
        prompt=prompt,
        max_tokens=100,  # Increased for more detailed messages
        temperature=0.3,
        stop=["\n"])

        message = response.choices[0].text.strip()
        logger.info(f"Generated commit message: '{message}'")

        # Validate the message matches conventional format
        if not any(message.startswith(prefix) for prefix in ["feat", "fix", "chore", "docs", "refactor", "test", "perf", "ci", "build", "style"]):
            logger.warning(f"Generated message '{message}' doesn't follow conventional format, applying fallback")
            message = "chore: update files based on recent changes"

        return message
    except Exception as e:
        error_msg = f"Error generating commit message: {e}"
        logger.error(error_msg)
        click.secho(error_msg, fg="red")
        return "chore: update project files"

def run_commands(commands: list[str]):
    for cmd in commands:
        if cmd == "__auto_commit__":
            logger.info("Executing auto-commit workflow")
            perform_auto_commit()
            continue

        click.secho(f"Running: {cmd}", fg="green")
        logger.info(f"Executing git command: '{cmd}'")
        try:
            result = subprocess.run(cmd.split(), check=True, capture_output=True, text=True)
            if result.stdout:
                logger.debug(f"Command output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            error_msg = f"Command failed: {e}\nOutput: {e.stderr}"
            logger.error(error_msg)
            click.secho(error_msg, fg="red")

def perform_auto_commit():
    logger.info("Starting auto-commit process")
    try:
        # Stage all changes
        logger.info("Staging all changes with 'git add .'")
        subprocess.run(["git", "add", "."], check=True, capture_output=True, text=True)

        # Get comprehensive diff for better commit message generation
        diff = get_git_diff_summary()
        if not diff or diff == "Files changed:\n\nDetails:\n":
            msg = "No staged changes to commit."
            logger.warning(msg)
            click.secho(msg, fg="yellow")
            return

        # Generate a meaningful commit message
        message = generate_commit_message(diff)
        click.echo(f"Generated commit message: {message}")

        # Perform the commit
        logger.info(f"Committing changes with message: '{message}'")
        result = subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True, text=True)
        click.secho(f"Successfully committed changes: {result.stdout}", fg="green")
        logger.info("Commit completed successfully")
    except subprocess.CalledProcessError as e:
        error_msg = f"Commit failed: {e}\nOutput: {e.stderr}"
        logger.error(error_msg)
        click.secho(error_msg, fg="red")

@click.command()
@click.argument("nl_command", nargs=-1)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(nl_command, verbose):
    """Run Git commands using natural language"""
    # Configure logging level based on verbosity
    if verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    logger.info("Starting git-ai CLI")

    if not nl_command:
        msg = "Please provide a natural language Git command."
        logger.warning(msg)
        click.echo(msg)
        return

    nl_text = " ".join(nl_command)
    logger.info(f"Processing natural language command: '{nl_text}'")
    commands = ask_llm(nl_text)

    if not commands:
        msg = "No valid git commands could be generated."
        logger.warning(msg)
        click.echo(msg)
        return

    # Pre-generate commit message for better user feedback if auto-commit is in the commands
    if "__auto_commit__" in commands:
        logger.info("Auto-commit detected, pre-generating commit message for user preview")
        # Stage files first to get the diff
        try:
            subprocess.run(["git", "add", "."], check=True, capture_output=True, text=True)
            diff = get_git_diff_summary()
            if diff and diff != "Files changed:\n\nDetails:\n":
                message = generate_commit_message(diff)
                click.secho(f"Will commit with message: '{message}'", fg="blue")
            else:
                click.secho("No changes detected to commit.", fg="yellow")
        except Exception as e:
            logger.error(f"Error pre-generating commit message: {e}")

    if click.confirm(f"Run these command(s)? {commands}", default=True):
        logger.info(f"User confirmed execution of commands: {commands}")
        run_commands(commands)
    else:
        logger.info("User aborted command execution")
        click.echo("Aborted.")

if __name__ == "__main__":
    main()

