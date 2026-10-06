**Implementing releases with the shared `release-operator.yml`**

This guide moves community releases into `openstack-k8s-operators/lightspeed-operator`. A tag such as `v0.0.3` runs a customized copy of the shared workflow, which builds and publishes images, creates a GitHub release, and proposes the community-operators PR.

The instructions are based on these local revisions:

| Repository | Revision |
| --- | --- |
| `lightspeed-operator` | `3d5f3a5f5df4f403fff244e87814afe08c25de2e` |
| `github-workflows-operators` | `cbb2d68b2fdd32d6023698bc237c16b546e96916` |

This is an implementation guide. The snippets below describe changes to make in those repositories; writing this guide does not install or publish them. The standalone extraction workflow remains available during migration.

**1. Establish the release layout**

Use a maintained fork of `redhat-cop/github-workflows-operators` for the shared-workflow changes. Keep the operator source in its existing repository. The caller must run from the operator repository because the shared workflow's checkouts use the caller's repository and ref. [GitHub documents this context and the permissions inherited by reusable workflows.](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations)

Start a development branch in each checkout. Do not create a release tag yet.

For the first migration, use `linux/amd64`, enable unit tests, and disable Helm and integration tests. The operator has `make test`, but no `make integration` or Helm targets.

For the example tag `v0.0.3`, the shared workflow's existing naming produces:

| Item | Value |
| --- | --- |
| Operator image | `quay.io/openstack-lightspeed/operator:v0.0.3` |
| Bundle image | `quay.io/openstack-lightspeed/operator-bundle:0.0.3` |
| Community directory | `operators/openstack-lightspeed-operator/0.0.3/` |
| GitHub release | `v0.0.3` |

Notice that the bundle image tag has **no leading `v`**. This differs from the current operator publishing workflow. Update any consumers that construct bundle tags accordingly. Use an actually unused version when executing the release steps below; `0.0.3` is only an example.

**2. Put static community metadata in the operator source**

In `lightspeed-operator/config/manifests/bases/openstack-lightspeed-operator.clusterserviceversion.yaml`, add or update these fields, preserving the rest of the CSV:

```yaml
metadata:
  annotations:
    support: Community
spec:
  displayName: OpenStack Lightspeed (Community)
```

Keep the template's placeholder version. `make bundle VERSION=...` generates the release version and CSV name. This direct edit makes all bundles generated from this source carry the community branding. Use a separate Kustomize overlay instead if another distribution must retain different branding.

`OPENSHIFT_LIGHTSPEED_OPERATOR_VERSION` is absent from this revision's code and manifests. Do not add it back or introduce a caller input for it.

The existing `make bundle` target already generates manifests, metadata, scorecard tests, and `bundle.Dockerfile`, and validates the generated bundle. The shared workflow changes in step 6 will enable image digest resolution and set the CSV's `containerImage` annotation before publishing.

Upgrade metadata remains specific to the community submission: step 8 adds `replaces` and `release-config.yaml` after consulting upstream history. Consequently, the PR's bundle gains that metadata after the published bundle image is built, as in the current extraction approach.

**3. Add the Dockerfile expected by the shared build**

Create `lightspeed-operator/ci.Dockerfile`:

```dockerfile
FROM registry.access.redhat.com/ubi10/ubi-minimal:latest
WORKDIR /
COPY bin/manager /manager
USER 65532:65532
ENTRYPOINT ["/manager"]
```

The shared workflow compiles `bin/manager` before building this image. In its `build-operator` job, add `CGO_ENABLED: "0"` to the existing `build code` step's `env`, alongside `GOOS` and `GOARCH`. This matches the static build used by the operator's current Dockerfile.

Also replace the `bin/` rule in `lightspeed-operator/.dockerignore` with:

```text
bin/*
!bin/manager
```

Without this exception, Docker cannot copy the compiled manager. Keep other ignore rules. [Docker's ignore-file documentation explains exclusion exceptions.](https://docs.docker.com/build/concepts/context/#dockerignore-files)

**4. Extend the shared workflow's interface**

All shared-workflow edits below are in your fork's `.github/workflows/release-operator.yml`. Preserve existing inputs and add these entries under `on.workflow_call.inputs`:

<!-- snippet: shared-inputs -->
```yaml
OPERATOR_NAME:
  description: Operator package and CSV name; defaults to the caller repository name
  type: string
  required: false
  default: ""
FORK_REPOSITORY:
  description: Community operators fork in owner/repository form
  type: string
  required: false
  default: ""
PR_AUTHOR_NAME:
  description: Contributor name for Git commits and sign-off
  type: string
  required: false
  default: ""
RELEASE_HELM:
  description: Build and publish Helm charts
  type: boolean
  required: false
  default: true
```

Keep the existing `PR_ACTOR` input; despite its name, it supplies the contributor's **email**.

Add these entries under `on.workflow_call.secrets`:

<!-- snippet: shared-secrets -->
```yaml
REDHATIO_USERNAME:
  description: Username for pulling related images from registry.redhat.io
  required: false
REDHATIO_PASSWORD:
  description: Password or service account token for registry.redhat.io
  required: false
```

They are optional in the reusable interface for other operators, but our caller must supply both because our manifests reference protected Red Hat images.

**5. Update shared setup without putting secrets in shell source**

In `setup` → `Setting Workflow Variables`, add this entry to the existing step `env`:

```yaml
OPERATOR_NAME: ${{ inputs.OPERATOR_NAME }}
```

Replace only its `repository_name=...` command with:

```bash
echo "repository_name=${OPERATOR_NAME:-${GITHUB_REPOSITORY##*/}}" >> "$GITHUB_OUTPUT"
```

The existing `repository_name` output then supplies the correct package name throughout bundle paths, artifact names, and community submission paths. Its value for this operator will be `openstack-lightspeed-operator`.

Replace the two initial secret-check steps with this step. The secret values themselves are passed to login and PR actions later; this check needs only booleans.

<!-- snippet: check-secrets -->
```yaml
- name: Check required credentials
  env:
    HAS_REGISTRY_CREDENTIALS: ${{ secrets.REGISTRY_USERNAME != '' && secrets.REGISTRY_PASSWORD != '' }}
    HAS_COMMUNITY_TOKEN: ${{ secrets.COMMUNITY_OPERATOR_PAT != '' }}
  run: |
    if [[ "$HAS_REGISTRY_CREDENTIALS" != true ]]; then
      echo "::error::Supply REGISTRY_USERNAME and REGISTRY_PASSWORD."
      exit 1
    fi
    if [[ "$HAS_COMMUNITY_TOKEN" != true ]]; then
      echo "::error::Supply COMMUNITY_OPERATOR_PAT."
      exit 1
    fi
```

Use `shell: bash` for this step if changing the job to a runner whose default shell differs from Bash. The existing Ubuntu job already uses Bash.

**6. Generate and validate the community bundle**

In `build-bundle`, add the following value to the existing job `env`:

```yaml
HAS_REDHAT_CREDENTIALS: ${{ secrets.REDHATIO_USERNAME != '' && secrets.REDHATIO_PASSWORD != '' }}
```

Immediately before `build bundle`, insert:

<!-- snippet: redhat-login -->
```yaml
- name: Log in to Red Hat registry
  if: ${{ env.HAS_REDHAT_CREDENTIALS == 'true' }}
  uses: redhat-actions/podman-login@50c2d9a331bb67c8fdab99b86455fad05e2e3252 # v2
  with:
    registry: registry.redhat.io
    username: ${{ secrets.REDHATIO_USERNAME }}
    password: ${{ secrets.REDHATIO_PASSWORD }}
```

Replace the `build bundle` step with:

<!-- snippet: build-bundle -->
```yaml
- name: Build community bundle
  shell: bash
  run: |
    set -euo pipefail
    make bundle \
      IMG="$OPERATOR_IMAGE_REPOSITORY:$OPERATOR_VERSION" \
      VERSION="$BUNDLE_VERSION" \
      CHANNELS=alpha DEFAULT_CHANNEL=alpha USE_IMAGE_DIGESTS=true

    csv="bundle/manifests/$REPOSITORY_NAME.clusterserviceversion.yaml"
    OPERATOR_IMAGE=$(yq -r '
      .spec.install.spec.deployments[].spec.template.spec.containers[] |
      select(.name == "manager") | .image
    ' "$csv")
    if [[ ! "$OPERATOR_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]; then
      echo "::error::Expected the generated manager image to use a digest."
      exit 1
    fi
    export OPERATOR_IMAGE
    yq -i '.metadata.annotations.containerImage = strenv(OPERATOR_IMAGE)' "$csv"
```

This annotation step matches the current operator's single `manager` container. The runner needs Mike Farah's `yq` v4, as used by our current standalone workflow.

Remove `Process Bundle for Disconnected Support`: the Makefile's existing `USE_IMAGE_DIGESTS=true` path now resolves the images. Keep the later `Copy bundle dockerfile`, bundle validation, image build, signing, scanning, and artifact-upload steps. Keep `operator-sdk bundle validate ./bundle --select-optional name=operatorhub` after the annotation change. [Operator SDK documents directory validation and its optional OperatorHub checks.](https://sdk.operatorframework.io/docs/cli/operator-sdk_bundle_validate/)

**7. Make Helm optional without skipping the release**

Keep the existing `needs` lists. Replace or add the **job-level** `if` conditions as follows:

| Job | `if` expression |
| --- | --- |
| `package-helm` | `${{ inputs.RELEASE_HELM }}` |
| `test-helmchart` | `${{ inputs.RELEASE_HELM && inputs.RUN_HELMCHART_TEST }}` |
| `build-operator` | `${{ !cancelled() && !failure() }}` |
| `process-operator-image-manifest` | `${{ !cancelled() && !failure() }}` |
| `build-bundle` | `${{ !cancelled() && !failure() }}` |
| `process-bundle-image-manifest` | `${{ !cancelled() && !failure() }}` |
| `provenance-operator` | `${{ !cancelled() && !failure() }}` |
| `provenance-bundle` | `${{ !cancelled() && !failure() }}` |
| `recombine-dist` | `${{ !cancelled() && !failure() }}` |
| `github-release` | `${{ !cancelled() && !failure() && needs.setup.outputs.tag_event == 'true' }}` |
| `helm-release` | `${{ !cancelled() && !failure() && inputs.RELEASE_HELM && needs.setup.outputs.tag_event == 'true' }}` |

In `setup`, also add `if: ${{ inputs.RELEASE_HELM }}` to the `Verify Semver Helm Chart Version` step. Leave `test-operator`'s existing condition on `RUN_UNIT_TESTS || RUN_INTEGRATION_TESTS` in place. Step 8 supplies the updated `operatorhub-release` condition.

These status functions allow intentionally skipped Helm/test jobs while preventing continuation after a failed or cancelled dependency. Simply adding `RELEASE_HELM: false` is insufficient: skipped dependencies propagate through `needs`. Do not use an unconditional `always()` for publishing. See [job dependencies](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs#defining-prerequisite-jobs) and [status-check functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions).

**8. Replace the shared community submission job**

Replace the entire existing `operatorhub-release` job with the following. It handles a new version of the already-registered OpenStack Lightspeed operator and keeps the current release branch naming.

This removes the unused PR-template loading, the duplicate first-release PR step, the deletion of `replaces`, and the unconditional copy of `config/community-operators/ci.yaml`. Therefore **no new `config/community-operators/` directory is required** for this implementation. Existing upstream `ci.yaml` remains authoritative.

Insert this job under `jobs`, with the same indentation as the other jobs:

<!-- snippet: operatorhub-release -->
```yaml
operatorhub-release:
  runs-on: ubuntu-24.04
  needs: [setup, test-operator, github-release, helm-release]
  if: >-
    ${{ !cancelled() && !failure() &&
        needs.setup.outputs.tag_event == 'true' &&
        needs.github-release.result == 'success' &&
        (!inputs.RELEASE_HELM || needs.helm-release.result == 'success') }}
  permissions:
    contents: read
  env:
    REPOSITORY_NAME: ${{ needs.setup.outputs.repository_name }}
    OPERATOR_VERSION: ${{ needs.setup.outputs.operator_version }}
    BUNDLE_VERSION: ${{ needs.setup.outputs.bundle_version }}
  steps:
    - name: Check out community operators
      uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
      with:
        repository: redhat-openshift-ecosystem/community-operators-prod
        ref: main
        path: community-operators-prod
        fetch-depth: 0
        sparse-checkout: operators/${{ env.REPOSITORY_NAME }}
        persist-credentials: false

    - name: Download release artifacts
      uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8
      with:
        name: dist
        path: dist

    - name: Prepare community submission
      id: prepare
      shell: bash
      run: |
        set -euo pipefail
        version_pattern='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
        [[ "$BUNDLE_VERSION" =~ $version_pattern ]]
        [[ "$REPOSITORY_NAME" =~ ^[a-z0-9][a-z0-9-]*$ ]]
        operator_dir="community-operators-prod/operators/$REPOSITORY_NAME"
        release_dir="$operator_dir/$BUNDLE_VERSION"
        if [[ -e "$release_dir" ]]; then
          echo "::error::Version $BUNDLE_VERSION already exists on upstream main."
          exit 1
        fi
        PREVIOUS_VERSION=$(
          { find "$operator_dir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n'; printf '%s\n' "$BUNDLE_VERSION"; } |
            grep -E "$version_pattern" | sort -Vu |
            awk -v version="$BUNDLE_VERSION" '$0 == version { print previous } { previous = $0 }'
        )
        : "${PREVIOUS_VERSION:?No community release precedes this version.}"
        export PREVIOUS_VERSION

        mkdir -p bundle "$release_dir"
        tar -xzf "dist/$REPOSITORY_NAME-bundle-$OPERATOR_VERSION-linux-amd64.tar.gz" \
          --strip-components=1 -C bundle
        for directory in manifests metadata tests; do
          cp -R "bundle/$directory" "$release_dir/$directory"
        done
        csv="$release_dir/manifests/$REPOSITORY_NAME.clusterserviceversion.yaml"
        yq -e '
          .metadata.name == (strenv(REPOSITORY_NAME) + ".v" + strenv(BUNDLE_VERSION)) and
          .spec.version == strenv(BUNDLE_VERSION)
        ' "$csv" >/dev/null
        yq -i '
          .spec.replaces = (strenv(REPOSITORY_NAME) + ".v" + strenv(PREVIOUS_VERSION))
        ' "$csv"
        cat > "$release_dir/release-config.yaml" <<EOF
        catalog_templates:
          - template_name: v4.16.yaml
            channels: [alpha]
            replaces: $REPOSITORY_NAME.v$PREVIOUS_VERSION
          - template_name: v4.18.yaml
            channels: [alpha]
            replaces: $REPOSITORY_NAME.v$PREVIOUS_VERSION
        EOF
        echo "operator_image=$(yq -r '.metadata.annotations.containerImage' "$csv")" >> "$GITHUB_OUTPUT"

    - name: Create or update community PR
      id: pr
      uses: peter-evans/create-pull-request@5f6978faf089d4d20b00c7766989d076bb2fc7f1 # v8
      with:
        token: ${{ secrets.COMMUNITY_OPERATOR_PAT }}
        path: community-operators-prod
        base: main
        branch: openstack-lightspeed-release-${{ env.BUNDLE_VERSION }}
        push-to-fork: ${{ inputs.FORK_REPOSITORY || format('{0}/community-operators-prod', github.repository_owner) }}
        add-paths: operators/${{ env.REPOSITORY_NAME }}/${{ env.BUNDLE_VERSION }}
        author: ${{ inputs.PR_AUTHOR_NAME || github.actor }} <${{ inputs.PR_ACTOR }}>
        committer: ${{ inputs.PR_AUTHOR_NAME || github.actor }} <${{ inputs.PR_ACTOR }}>
        signoff: true
        commit-message: operator ${{ env.REPOSITORY_NAME }} (${{ env.BUNDLE_VERSION }})
        title: operator ${{ env.REPOSITORY_NAME }} (${{ env.BUNDLE_VERSION }})
        body: |
          Release ${{ env.REPOSITORY_NAME }} ${{ env.BUNDLE_VERSION }}.

          - Source: ${{ github.server_url }}/${{ github.repository }}/tree/${{ github.ref_name }}
          - Operator image: ${{ steps.prepare.outputs.operator_image }}
          - Bundle image: ${{ inputs.BUNDLE_IMAGE_REPOSITORY }}:${{ env.BUNDLE_VERSION }}

          Generated by [this run](${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}).

    - name: Show pull request
      env:
        PR_URL: ${{ steps.pr.outputs.pull-request-url }}
      run: |
        printf 'Community PR: %s\n' "$PR_URL" >> "$GITHUB_STEP_SUMMARY"
```

The catalog templates above preserve our current `v4.16.yaml` and `v4.18.yaml` targets. Change them deliberately if the supported catalog set changes. This job requires the `linux/amd64` artifact, so retain that platform when expanding the build matrix.

The PR action can regenerate its managed branch on reruns. Finish or coordinate any existing PR for the same version before switching workflows. [The action's documentation describes its branch-update behavior.](https://github.com/peter-evans/create-pull-request/blob/main/docs/concepts-guidelines.md)

**9. Configure credentials and release variables in the operator repository**

Under the operator repository's **Settings → Secrets and variables → Actions**, configure:

| Kind | Name | Purpose |
| --- | --- | --- |
| Secret | `COMMUNITY_OPERATORS_TOKEN` | Push to the community fork and open/update upstream PRs. Use the same permissions as the current standalone release token. |
| Secret | `QUAY_USERNAME` | Account or robot account with push access to the operator, bundle, and optional catalog repositories. |
| Secret | `QUAY_PASSWORD` | Corresponding Quay credential. |
| Secret | `REDHATIO_USERNAME` | Account with pull access to the related Red Hat images. |
| Secret | `REDHATIO_PASSWORD` | Corresponding Red Hat registry credential. |
| Variable | `COMMUNITY_OPERATORS_FORK` | For example, `jancervenka/community-operators-prod`; it must be an existing fork. |
| Variable | `RELEASE_AUTHOR_NAME` | Contributor's name for commits and sign-off. |
| Variable | `RELEASE_AUTHOR_EMAIL` | Corresponding commit and sign-off email. |

The operator's current workflow already references the Quay and Red Hat registry secrets. Check their availability to this repository; secrets from the standalone release repository are not automatically transferred.

For creating `COMMUNITY_OPERATORS_TOKEN` and choosing its scopes, follow the [existing token setup instructions](../README.md#one-time-setup), then save the token as a secret in the operator repository.

Allow the chosen reusable workflow and its actions in the repository's Actions settings. If it is hosted in a fork, confirm that the caller can access it. The caller below grants the shared jobs the permissions they request for GitHub releases, signatures, and provenance.

**10. Add the release caller to the operator repository**

After reviewing and publishing the customized shared workflow, obtain its full commit SHA. Create `lightspeed-operator/.github/workflows/release.yaml` with the following content.

Replace **both** `YOUR_WORKFLOW_OWNER` and `REPLACE_WITH_REVIEWED_COMMIT_SHA` in `uses` before committing the caller. These are placeholders, not existing references. Pin the reviewed customization; calling the unmodified upstream workflow will not accept the new inputs.

<!-- snippet: caller -->
```yaml
name: Release community operator

on:
  push:
    tags: ['v*']
  workflow_dispatch: {}

permissions:
  contents: read

concurrency:
  group: community-operator-release
  cancel-in-progress: false

jobs:
  validate-release:
    runs-on: ubuntu-24.04
    env:
      FORK_REPOSITORY: ${{ vars.COMMUNITY_OPERATORS_FORK }}
      AUTHOR_NAME: ${{ vars.RELEASE_AUTHOR_NAME }}
      AUTHOR_EMAIL: ${{ vars.RELEASE_AUTHOR_EMAIL }}
      HAS_REDHAT_CREDENTIALS: ${{ secrets.REDHATIO_USERNAME != '' && secrets.REDHATIO_PASSWORD != '' }}
    steps:
      - name: Validate release settings
        shell: bash
        run: |
          set -euo pipefail
          if [[ "$GITHUB_REF_TYPE" != tag || ! "$GITHUB_REF_NAME" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
            echo "::error::Run this workflow on a tag named vX.Y.Z."
            exit 1
          fi
          : "${AUTHOR_NAME:?Set RELEASE_AUTHOR_NAME.}"
          : "${AUTHOR_EMAIL:?Set RELEASE_AUTHOR_EMAIL.}"
          if [[ ! "$FORK_REPOSITORY" =~ ^[a-zA-Z0-9-]+/[a-zA-Z0-9_.-]+$ ]]; then
            echo "::error::Set COMMUNITY_OPERATORS_FORK to owner/repository."
            exit 1
          fi
          if [[ "$HAS_REDHAT_CREDENTIALS" != true ]]; then
            echo "::error::Set REDHATIO_USERNAME and REDHATIO_PASSWORD."
            exit 1
          fi

  release:
    needs: validate-release
    permissions:
      contents: write
      actions: read
      id-token: write
      packages: write
    uses: YOUR_WORKFLOW_OWNER/github-workflows-operators/.github/workflows/release-operator.yml@REPLACE_WITH_REVIEWED_COMMIT_SHA
    with:
      OPERATOR_NAME: openstack-lightspeed-operator
      OPERATOR_IMAGE_REPOSITORY: quay.io/openstack-lightspeed/operator
      BUNDLE_IMAGE_REPOSITORY: quay.io/openstack-lightspeed/operator-bundle
      GO_VERSION: '1.26.3'
      OPERATOR_SDK_VERSION: v1.42.3
      BUILD_PLATFORMS: linux/amd64
      RELEASE_HELM: false
      RUN_UNIT_TESTS: true
      RUN_INTEGRATION_TESTS: false
      RUN_HELMCHART_TEST: false
      FORK_REPOSITORY: ${{ vars.COMMUNITY_OPERATORS_FORK }}
      PR_AUTHOR_NAME: ${{ vars.RELEASE_AUTHOR_NAME }}
      PR_ACTOR: ${{ vars.RELEASE_AUTHOR_EMAIL }}
    secrets:
      COMMUNITY_OPERATOR_PAT: ${{ secrets.COMMUNITY_OPERATORS_TOKEN }}
      REGISTRY_USERNAME: ${{ secrets.QUAY_USERNAME }}
      REGISTRY_PASSWORD: ${{ secrets.QUAY_PASSWORD }}
      REDHATIO_USERNAME: ${{ secrets.REDHATIO_USERNAME }}
      REDHATIO_PASSWORD: ${{ secrets.REDHATIO_PASSWORD }}
```

Update the Go and SDK inputs when the operator's requirements change. The values above match the inspected source.

The tag event starts the full publishing pipeline. A manual dispatch must also target an existing `vX.Y.Z` tag; running it against `main` intentionally fails validation. `concurrency` serializes release runs, but it is not a durable queue for a burst of tags. Publish and monitor one release at a time.

**11. Preserve the catalog and development image workflow**

For the smallest migration, keep the existing `build-and-push.yaml` for development builds on `main`. Add the new caller for release tags. The shared workflow publishes versioned operator/bundle images and also updates their `latest` tags; development builds can subsequently move those tags again. Deploy releases using versioned references or digests.

The existing workflow still publishes the development catalog. If you also want a catalog image for each release tag, append this job under the caller's `jobs`:

<!-- snippet: catalog -->
```yaml
catalog:
  needs: release
  runs-on: ubuntu-24.04
  permissions:
    contents: read
  steps:
    - name: Check out release source
      uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
      with:
        persist-credentials: false

    - name: Set up Go
      uses: actions/setup-go@b7ad1dad31e06c5925ef5d2fc7ad053ef454303e # v7
      with:
        go-version-file: go.mod

    - name: Log in to Quay
      uses: redhat-actions/podman-login@50c2d9a331bb67c8fdab99b86455fad05e2e3252 # v2
      with:
        registry: quay.io
        username: ${{ secrets.QUAY_USERNAME }}
        password: ${{ secrets.QUAY_PASSWORD }}

    - name: Build and publish release catalog
      shell: bash
      run: |
        set -euo pipefail
        version="${GITHUB_REF_NAME#v}"
        make catalog-build catalog-push \
          VERSION="$version" \
          BUNDLE_IMG="quay.io/openstack-lightspeed/operator-bundle:$version" \
          CATALOG_IMG="quay.io/openstack-lightspeed/operator-catalog:$GITHUB_REF_NAME"
```

This retains the existing catalog Makefile implementation. It creates a catalog containing the specified bundle, matching the current default `catalog-build` behavior; maintaining a catalog with multiple historical bundles is a separate policy. This optional catalog job runs after the shared workflow, so a catalog failure does not undo already-published images or the community PR. It does not add the shared workflow's image-signing/provenance steps to the catalog.

**12. Validate the changes before creating a release tag**

For local validation, have Go matching `go.mod`, Make, Podman, Mike Farah's `yq` v4, and `actionlint` available. The Makefile downloads its build tools, including Operator SDK when it is not already on `PATH`; if you use an installed SDK, select `v1.42.3`.

Run these from `lightspeed-operator`:

```bash
make test
CGO_ENABLED=0 make build
podman build -f ci.Dockerfile -t localhost/openstack-lightspeed-release-check .
```

The build check exercises the new Dockerfile and `.dockerignore` exception without pushing an image.

For a local bundle check, log in to the Red Hat registry through its normal interactive or password-stdin flow, select an existing operator image built from the source you are checking, and run:

```bash
# Replace this with a real published digest matching the checked-out source.
OPERATOR_IMAGE='quay.io/openstack-lightspeed/operator@sha256:REPLACE_WITH_ACTUAL_DIGEST'
make bundle IMG="$OPERATOR_IMAGE" VERSION=0.0.3 \
  CHANNELS=alpha DEFAULT_CHANNEL=alpha USE_IMAGE_DIGESTS=true
```

Set the annotation from the generated manager image, then run the additional bundle checks:

```bash
csv=bundle/manifests/openstack-lightspeed-operator.clusterserviceversion.yaml
OPERATOR_IMAGE=$(yq -r '
  .spec.install.spec.deployments[].spec.template.spec.containers[] |
  select(.name == "manager") | .image
' "$csv")
export OPERATOR_IMAGE
yq -i '.metadata.annotations.containerImage = strenv(OPERATOR_IMAGE)' "$csv"

# The Makefile uses an installed SDK or downloads it to bin/operator-sdk.
sdk=$(command -v operator-sdk || printf '%s' "$PWD/bin/operator-sdk")
"$sdk" bundle validate ./bundle --select-optional name=operatorhub
git diff --check
```

`make bundle` modifies generated configuration in the checkout. Review those changes before committing; do not commit an example release image reference accidentally. Check that `bundle/manifests`, `bundle/metadata`, `bundle/tests`, and `bundle.Dockerfile` are produced.

Run `actionlint .github/workflows/release.yaml` in the operator repository. In the shared-workflow fork, run `actionlint -shellcheck= .github/workflows/release-operator.yml` for workflow structure and expressions, then run normal `actionlint` to review shell diagnostics. The inspected shared workflow already has shell-quoting warnings; distinguish those from new errors instead of disabling validation permanently.

Before the first tag, verify the following behavior in review or a disposable fixture:

- With Helm disabled and tests successful, `recombine-dist`, `github-release`, and `operatorhub-release` are eligible to run.
- A failed test/build or cancellation prevents downstream publishing.
- With existing directories `0.0.2`, `0.0.10`, and `0.0.12`, submitting `0.0.11` selects `0.0.10` as its predecessor.
- A version already on upstream `main` is rejected.
- The PR contains only the new operator version directory, including its tests and `release-config.yaml`.

For an end-to-end rehearsal, use a fork of the operator repository and temporary public Quay repositories, with working credentials and real version tags. The workflow has no dry-run switch: it publishes images/releases and opens a real upstream PR. If you need a rehearsal without an upstream PR, temporarily disable `operatorhub-release` in a separate test revision of the shared workflow, then restore it before pinning the production caller.

**13. Merge in order and run the first release**

First review and publish the shared-workflow customization. Record the final commit SHA, update the caller's `uses` to that SHA, and merge the operator changes. The source commit you tag must contain the caller, CSV changes, `ci.Dockerfile`, and `.dockerignore` update.

Before tagging, check upstream `operators/openstack-lightspeed-operator/` and choose a new version with a valid predecessor. The PR-stage duplicate check runs after image publication, so this check avoids publishing a version that cannot be submitted.

From the operator repository, after selecting the release commit:

```bash
git switch main
git pull --ff-only
git status --short

# Example only: choose an unused version and review HEAD before tagging.
RELEASE_VERSION=0.0.3
git tag -a "v$RELEASE_VERSION" -m "Release OpenStack Lightspeed $RELEASE_VERSION"
git push origin "refs/tags/v$RELEASE_VERSION"
```

Pushing the tag launches the release. Follow the Actions run and confirm the unit tests, image builds, signing/provenance jobs, bundle validation, GitHub release, and community PR complete. If enabled, check the release catalog job as well.

Review the generated PR before merging it upstream: package/version, image digests, community branding, `spec.replaces`, both catalog templates, and the signed-off commit. The upstream community pipeline performs its own checks after submission. [Its contribution guide describes the PR process.](https://redhat-openshift-ecosystem.github.io/operator-pipelines/users/contributing-via-pr/)

After the first successful migration release, disable or remove the old standalone `propose-release.yml` so the same version is not submitted through two release paths.

**14. Handle failures and subsequent releases**

| Symptom | What to check |
| --- | --- |
| `No such remote: 'fork'` during PR cleanup | Expand the earlier action log. `Bad credentials` indicates an invalid PAT; replace the secret rather than manually creating a Git remote. |
| `COPY bin/manager` fails | Confirm `make` produced the binary and `.dockerignore` includes it. |
| PR looks for `lightspeed-operator.clusterserviceversion.yaml` | Ensure `OPERATOR_NAME` reaches the existing `repository_name` setup output. |
| Release jobs are skipped after Helm is skipped | Check all job conditions from step 7, not only `helm-release`. |
| Registry authorization fails while resolving images | Check `REDHATIO_*` credentials and their pull access to every referenced Red Hat image. |
| GitHub release or OIDC signing fails for lack of permission | Check the caller's `release.permissions` and organization policies. |
| Bundle artifact is missing | Confirm `linux/amd64` is included and the archive name uses the operator tag, such as `v0.0.3`. |
| Catalog cannot find the release bundle | Use bundle tag `0.0.3`, without the leading `v`. |
| Version already exists upstream | Choose a new release version; the workflow does not overwrite a merged release. |

For transient infrastructure or credential failures, use **Re-run failed jobs** where appropriate. Re-running the full workflow can rebuild and overwrite that version's image tags, and the PR action can replace manual changes on its branch. For source changes, create a new version rather than moving an existing release tag. Once a version is merged upstream, its submission job will reject another run for that version.

The documented snippets can be checked locally, but the complete release still needs an authenticated GitHub Actions run to verify registry access, signatures, publishing, and upstream PR permissions.
