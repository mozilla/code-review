from urllib.parse import urlparse

import structlog
from git import Repo

logger = structlog.getLogger(__name__)


def build_repo_slug(repo_url):
    """
    Build a slug from a github repository url
    mozilla-firefox/firefox would become mozilla-firefox_firefox
    This method copies the automatic slug creation in backend's RepositoryGetOrCreateField serializer field.
    """
    parts = urlparse(repo_url)
    assert parts.netloc == "github.com", "Only github repositories are supported"

    path = parts.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]

    return path.replace("/", "_")


def git_clone(base_repository, head_repository, revision, destination):
    """
    Clone a git repo at a specific revision in a directory
    If the repo is already present, fetches and checkout
    """

    # Build slug
    base_slug = build_repo_slug(base_repository)
    head_slug = build_repo_slug(head_repository)

    # Clone or fetch upstream
    path = destination / base_slug
    if path.exists() and (path / ".git").is_dir():
        logger.info("Use existing repo", path=path)
        repo = Repo.init(path)

        # Make sure origin matches the url
        origin = repo.remotes["origin"]
        if origin.url != base_repository:
            logger.info("Update remote origin", url=base_repository)
            origin.set_url(base_repository)

        # Always update the references for base repo
        logger.info("Fetch remote origin")
        origin.fetch()
    else:
        logger.info("Clone git repository", url=base_repository, path=path)
        repo = Repo.clone_from(base_repository, path)

    # Fetch head repository as a remote on top of base
    try:
        head = repo.remotes[head_slug]

        # Make sure head matches the url
        if head.url != head_repository:
            head.set_url(head_repository)

    except IndexError:
        # Setup new remote
        head = repo.create_remote(head_slug, head_repository)

    # Always fetch, as creating a remote does not fetch automatically
    logger.info("Fetch remote head", url=head.url)
    head.fetch()

    # Detach head to specified revision
    logger.info("Checkout to head", revision=revision)
    repo.head.reference = repo.commit(revision)

    return repo
