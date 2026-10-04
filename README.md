# OpenStack Lightspeed community releases

The **Propose community operator release** GitHub Actions workflow extracts a
bundle with `init.sh`, updates it with `main.py`, pushes a release branch to your
fork, and opens a pull request against
[`redhat-openshift-ecosystem/community-operators-prod:main`](https://github.com/redhat-openshift-ecosystem/community-operators-prod).

## One-time setup

1. Push this repository, including `.github/workflows/propose-release.yml`, the
   scripts, `pyproject.toml`, `uv.lock`, and `.python-version`, to GitHub. The
   workflow must be on the repository's default branch to appear under Actions.
2. Create a fork of `redhat-openshift-ecosystem/community-operators-prod` under a
   user or organization where your automation account can push branches.
3. In this repository's **Settings → Secrets and variables → Actions**, add:

   | Kind | Name | Value |
   | --- | --- | --- |
   | Secret | `COMMUNITY_OPERATORS_TOKEN` | A classic personal access token with `public_repo` scope from an account that can push to the fork and open upstream PRs. |
   | Variable | `RELEASE_AUTHOR_NAME` | Contributor's real name for the Git author and commit sign-off. |
   | Variable | `RELEASE_AUTHOR_EMAIL` | Corresponding Git author and sign-off email. |

   The token may also need `workflow` scope when pushing upstream history that
   introduces workflow changes to the fork. Authorize the token for organization
   SSO if required by the fork's organization. The built-in `GITHUB_TOKEN` is
   scoped to this repository and cannot publish to your separate fork.
   See [GitHub's token documentation](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
   for token types and organization restrictions.

   Commits use this identity for the
   [sign-off required by upstream](https://redhat-openshift-ecosystem.github.io/operator-pipelines/users/contributing-prerequisites/#sign-your-work).

## Launch a release

Open **Actions → Propose community operator release → Run workflow** and fill in:

| Input | Example | Meaning |
| --- | --- | --- |
| `new_version` | `0.0.3` | New community version, in `X.Y.Z` form. |
| `container_image_tag` | `latest` | Existing tag in both `quay.io/openstack-lightspeed/operator-bundle` and `quay.io/openstack-lightspeed/operator`. Prefer an immutable release tag for reproducible runs. |
| `openshift_lightspeed_operator_version` | `1.0.9` | Value written to `OPENSHIFT_LIGHTSPEED_OPERATOR_VERSION` in the CSV. |
| `fork_repository` | `your-account/community-operators-prod` | Existing fork that receives the release branch. |

The workflow uses Ubuntu, Podman, Python 3.12, and the dependencies in `uv.lock`.
Images must be publicly pullable. It creates
`openstack-lightspeed-release-<new_version>` from upstream `main`, commits only
the new version directory with a sign-off, and prints the PR URL in the run
summary. The previous version is the highest existing version below the new one.

Rerunning the same version resumes the branch in your fork, refreshes the bundle,
and adds a commit only if files changed. An existing open PR is reused. Pushes
never force-update the branch. Runs for the same fork and version are serialized;
a version already present on upstream `main` is rejected.

The workflow prepares and submits the bundle; it does not run `check.sh`, whose
scorecard command requires a configured Kubernetes cluster. The upstream
[community operator pipeline](https://redhat-openshift-ecosystem.github.io/operator-pipelines/users/contributing-via-pr/)
runs its checks on the submitted PR.

## Run locally

Install Git, Podman, and [uv](https://docs.astral.sh/uv/), then run:

```bash
export REPO_PATH=/tmp/community-operators-prod
bash init.sh 0.0.3 latest
uv run --locked main.py \
  --new-version 0.0.3 \
  --openshift-lightspeed-operator-version 1.0.9 \
  --image-tag latest
```

`init.sh` clones upstream when `REPO_PATH` does not exist and creates or checks
out the release branch. An existing checkout must be clean. `REPO_URL` and
`BASE_BRANCH` can override its clone source and base branch. `main.py` accepts
`--repo-path`, which defaults to `REPO_PATH` or `/tmp/community-operators-prod`.
Local runs leave changes uncommitted for inspection.

Run the local regression checks with:

```bash
uv run --locked python -m unittest discover -s tests -v
```
