# OpenStack Lightspeed community releases

All release automation lives in
[`propose-release.yml`](.github/workflows/propose-release.yml). It extracts an
existing bundle image, updates the community CSV and release configuration, and
uses Git and the GitHub CLI (`gh`) to commit the changes, push a release branch
to your fork, and open or update a PR against
[`redhat-openshift-ecosystem/community-operators-prod:main`](https://github.com/redhat-openshift-ecosystem/community-operators-prod).

For a future migration to source-based releases in the operator repository, see
the [step-by-step shared-workflow implementation guide](docs/reuse-release-operator.md).

## One-time setup

1. Add `.github/workflows/propose-release.yml` to your repository's default
   branch. This is the only file needed to run the workflow.
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

   The personal access token is passed as `GH_TOKEN` only to the PR step.
   [`gh auth setup-git`](https://cli.github.com/manual/gh_auth_setup-git) configures
   Git to authenticate through the CLI; the token is not placed in remote URLs
   or printed by the script. The bundle preparation script receives only a
   boolean indicating whether it is set.

## Launch a release

Open **Actions → Propose community operator release → Run workflow** and fill in:

| Input | Example | Meaning |
| --- | --- | --- |
| `new_version` | `0.0.3` | New community version, in `X.Y.Z` form. |
| `container_image_tag` | `latest` | Existing tag in both `quay.io/openstack-lightspeed/operator-bundle` and `quay.io/openstack-lightspeed/operator`. Prefer an immutable release tag for reproducible runs. |
| `fork_repository` | `your-account/community-operators-prod` | Existing fork that receives the release branch. |

The workflow uses Bash, Git, gh, Podman, curl, jq, and yq provided by the Ubuntu runner.
Images must be publicly pullable and the bundle must contain `/manifests`,
`/metadata`, and `/tests`. It creates
`openstack-lightspeed-release-<new_version>` from upstream `main`, commits only
the new version directory with a sign-off, and prints the PR URL in the run
summary. The previous version is the highest existing version below the new one.

Rerunning the same version regenerates the release from upstream `main` and
updates the existing PR. The script manages the release branch and may replace
manual edits on that branch when updating it. It uses `--force-with-lease` to
reject a push if the branch changes after it is read. Runs for the same fork and
version are serialized; a version already present on upstream `main` is rejected.

The fork's `main` branch does not need to be synchronized: each release starts
from the upstream checkout. PR lookup, creation, and updates use
[`gh api`](https://cli.github.com/manual/gh_api) with an explicit fork owner and
branch, supporting both personal and organization forks.

The upstream
[community operator pipeline](https://redhat-openshift-ecosystem.github.io/operator-pipelines/users/contributing-via-pr/)
runs its checks on the submitted PR.
