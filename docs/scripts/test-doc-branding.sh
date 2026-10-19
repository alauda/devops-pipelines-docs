#!/usr/bin/env bash
set -euo pipefail

# Repository root at the same depth in the synchronized docs tree.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

# Required attribution text shared by source and rendered checks.
notice_phrases=(
  "Tekton™ is a trademark of The Linux Foundation."
  "Red Hat® and OpenShift® are registered trademarks of Red Hat, Inc. in the United States and other countries."
  "Alauda is an independent vendor. This product is not affiliated with, endorsed by, or sponsored by The Linux Foundation or Red Hat, Inc. All trademarks are the property of their respective owners and are used here for identification purposes only."
)

# Source pages that must carry each attribution notice.
source_pages=(
  "docs/en/overview/intro.mdx"
  "docs/en/overview/release_notes.mdx"
  "docs/en/chains/intro.mdx"
  "docs/en/install.mdx"
  "docs/en/pipelines/quick_start.mdx"
)

# Rendered output paths corresponding to the source pages.
rendered_pages=(
  "dist/overview/intro"
  "dist/overview/release_notes"
  "dist/chains/intro"
  "dist/install"
  "dist/pipelines/quick_start"
)

for page in "${source_pages[@]}"; do
  for phrase in "${notice_phrases[@]}"; do
    if ! grep -Fq -- "$phrase" "$page"; then
      echo "Missing attribution in source: $page" >&2
      exit 1
    fi
  done
done

for page in "${rendered_pages[@]}"; do
  for extension in html md; do
    # Rendered filename for this format.
    output="${page}.${extension}"
    if [[ ! -f "$output" ]]; then
      echo "Missing rendered documentation output: $output" >&2
      exit 1
    fi
    for phrase in "${notice_phrases[@]}"; do
      if ! grep -Fq -- "$phrase" "$output"; then
        echo "Missing attribution in rendered output: $output" >&2
        exit 1
      fi
    done
  done
done

echo "Documentation attribution coverage passed for ${#source_pages[@]} pages."
