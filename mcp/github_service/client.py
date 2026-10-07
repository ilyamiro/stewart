import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

from github import Github, Auth
from github.GithubException import GithubException, BadCredentialsException

logger = logging.getLogger("github_service")

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
TOKEN_FILE = Path.home() / ".config" / "life" / "github_token.txt"


def load_dotenv():
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v


load_dotenv()


def get_token() -> Optional[str]:
    """Retrieve GitHub token from env, .env, token file, or gh CLI."""
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        return token.strip()

    load_dotenv()
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        return token.strip()

    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                t = f.read().strip()
                if t:
                    return t
        except Exception:
            pass

    try:
        res = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    return None


class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self._custom_token = token
        self._gh: Optional[Github] = None

    @property
    def token(self) -> Optional[str]:
        return self._custom_token or get_token()

    def get_gh(self) -> Github:
        t = self.token
        if not t:
            raise ValueError(
                "GitHub token not found. Please set GITHUB_TOKEN in .env, run 'bin/github-auth', or call 'github_set_token'."
            )
        if self._gh is None:
            self._gh = Github(auth=Auth.Token(t))
        return self._gh

    def check_auth(self) -> Dict[str, Any]:
        """Check authentication status with GitHub."""
        t = self.token
        if not t:
            return {
                "authenticated": False,
                "message": (
                    "Not authenticated with GitHub. Please provide a Personal Access Token via 'github_set_token', "
                    "add GITHUB_TOKEN to .env, or run 'bin/github-auth' in your terminal."
                )
            }

        try:
            gh = self.get_gh()
            user = gh.get_user()
            return {
                "authenticated": True,
                "user": {
                    "login": user.login,
                    "name": user.name,
                    "email": user.email,
                    "bio": user.bio,
                    "public_repos": user.public_repos,
                    "total_private_repos": getattr(user, "total_private_repos", 0),
                    "followers": user.followers,
                    "following": user.following,
                    "html_url": user.html_url
                },
                "message": f"Successfully authenticated as {user.login} ({user.name or ''})."
            }
        except BadCredentialsException:
            return {
                "authenticated": False,
                "error": "Bad credentials: The provided GitHub token is invalid or expired."
            }
        except Exception as e:
            return {
                "authenticated": False,
                "error": str(e)
            }

    def set_token(self, token: str) -> Dict[str, Any]:
        """Save a new GitHub token and verify authentication."""
        clean_token = token.strip()
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(clean_token)

        self._custom_token = clean_token
        self._gh = None
        return self.check_auth()

    def list_repos(
        self,
        visibility: str = "all",
        sort: str = "updated",
        limit: int = 20
    ) -> Dict[str, Any]:
        """List repositories for the authenticated user."""
        gh = self.get_gh()
        user = gh.get_user()

        repos = []
        for r in user.get_repos(visibility=visibility, sort=sort):
            repos.append({
                "id": r.id,
                "name": r.name,
                "full_name": r.full_name,
                "description": r.description,
                "private": r.private,
                "html_url": r.html_url,
                "stars": r.stargazers_count,
                "forks": r.forks_count,
                "language": r.language,
                "open_issues_count": r.open_issues_count,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None
            })
            if len(repos) >= limit:
                break

        return {
            "user": user.login,
            "total_retrieved": len(repos),
            "repos": repos
        }

    def get_repo_info(self, repo_name: str) -> Dict[str, Any]:
        """Get details about a specific repository (e.g. 'owner/repo')."""
        gh = self.get_gh()
        r = gh.get_repo(repo_name)
        return {
            "id": r.id,
            "name": r.name,
            "full_name": r.full_name,
            "description": r.description,
            "private": r.private,
            "html_url": r.html_url,
            "default_branch": r.default_branch,
            "stars": r.stargazers_count,
            "forks": r.forks_count,
            "language": r.language,
            "open_issues_count": r.open_issues_count,
            "topics": r.get_topics(),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None
        }

    def list_issues(
        self,
        repo_name: Optional[str] = None,
        state: str = "open",
        limit: int = 20
    ) -> Dict[str, Any]:
        """List issues across repositories or for a specific repo."""
        gh = self.get_gh()

        issues = []
        if repo_name:
            repo = gh.get_repo(repo_name)
            issue_paginated = repo.get_issues(state=state)
        else:
            issue_paginated = gh.get_user().get_issues(state=state)

        for issue in issue_paginated:
            is_pr = issue.pull_request is not None
            issues.append({
                "number": issue.number,
                "title": issue.title,
                "state": issue.state,
                "user": issue.user.login if issue.user else "unknown",
                "labels": [label.name for label in issue.labels],
                "comments_count": issue.comments,
                "is_pull_request": is_pr,
                "created_at": issue.created_at.isoformat() if issue.created_at else None,
                "html_url": issue.html_url
            })
            if len(issues) >= limit:
                break

        return {
            "repo": repo_name or "all",
            "total_retrieved": len(issues),
            "issues": issues
        }

    def create_issue(
        self,
        repo_name: str,
        title: str,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create an issue in a repository."""
        gh = self.get_gh()
        repo = gh.get_repo(repo_name)
        kwargs: Dict[str, Any] = {"title": title}
        if body:
            kwargs["body"] = body
        if labels:
            kwargs["labels"] = labels

        issue = repo.create_issue(**kwargs)
        return {
            "status": "created",
            "number": issue.number,
            "title": issue.title,
            "html_url": issue.html_url,
            "message": f"Successfully created issue #{issue.number} in {repo_name}."
        }

    def list_pull_requests(
        self,
        repo_name: str,
        state: str = "open",
        limit: int = 20
    ) -> Dict[str, Any]:
        """List pull requests for a repository."""
        gh = self.get_gh()
        repo = gh.get_repo(repo_name)

        prs = []
        for pr in repo.get_pulls(state=state):
            prs.append({
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "user": pr.user.login if pr.user else "unknown",
                "head": pr.head.ref,
                "base": pr.base.ref,
                "draft": pr.draft,
                "created_at": pr.created_at.isoformat() if pr.created_at else None,
                "html_url": pr.html_url
            })
            if len(prs) >= limit:
                break

        return {
            "repo": repo_name,
            "total_retrieved": len(prs),
            "pull_requests": prs
        }

    def get_notifications(
        self,
        all: bool = False,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Fetch notifications across user's repositories."""
        gh = self.get_gh()
        user = gh.get_user()

        notifications = []
        for n in user.get_notifications(all=all):
            notifications.append({
                "id": n.id,
                "repository": n.repository.full_name if n.repository else None,
                "subject_title": n.subject.title if n.subject else None,
                "subject_type": n.subject.type if n.subject else None,
                "reason": n.reason,
                "unread": n.unread,
                "updated_at": n.updated_at.isoformat() if n.updated_at else None
            })
            if len(notifications) >= limit:
                break

        return {
            "total_notifications": len(notifications),
            "notifications": notifications
        }


_github_client: Optional[GitHubClient] = None


def get_github_client() -> GitHubClient:
    global _github_client
    if _github_client is None:
        _github_client = GitHubClient()
    return _github_client
