# shellcheck shell=bash disable=SC2016
# Shared by hooks/environment and bin/git-remote-entire. Prints only fixed text,
# never credentials or agent output.
#
# entire_source: supplied | issued | job | none (where ENTIRE_TOKEN came from)
# entire_reason: why Buildkite did not issue credentials, when it did not:
#   opt-in | provider | repository | unknown

entire_settings_url() {
  local org=${BUILDKITE_ORGANIZATION_SLUG:-}
  [[ $org =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] || org='~'
  echo "https://buildkite.com/organizations/${org}/repository-providers"
}

# What Buildkite said, and the fix that addresses it.
entire_reason_guidance() {
  local setting='"Allow self-hosted agents to use checkout credentials"'
  case ${entire_reason:-unknown} in
    opt-in)
      echo "Entire: Buildkite did not issue credentials because ${setting} is off for this pipeline's Entire repository provider."
      echo "Entire:   - Turn it on: $(entire_settings_url)" ;;
    provider)
      echo "Entire: Buildkite allowed this job, but could not get a token for this repository from Entire. The self-hosted setting is not the cause."
      echo 'Entire:   - Retry the job. If it keeps failing, contact Buildkite support.' ;;
    repository)
      echo "Entire: Buildkite did not issue credentials because BUILDKITE_REPO does not match this pipeline's Entire repository."
      echo "Entire:   - Check the pipeline's repository setting." ;;
    *)
      echo 'Entire: Buildkite did not issue credentials; see the warning from the environment hook.'
      if [[ ${BUILDKITE_COMPUTE_TYPE:-} == hosted ]]; then
        echo 'Entire:   - Retry the job. If it keeps failing, contact Buildkite support.'
      else
        echo "Entire:   - On self-hosted agents, check that ${setting} is on: $(entire_settings_url)"
      fi ;;
  esac
}

# entire_guidance KIND, where KIND is how authentication failed:
#   guard    - no token, and ENTIRE_GIT_NO_LOGIN_FALLBACK forbids saved login
#   missing  - the helper found no token and no saved login
#   rejected - Entire rejected the token or saved login that was used
#   other    - the helper failed for another reason
entire_guidance() {
  case $1:${entire_source:-none} in
    guard:*)
      echo '+++ :warning: Entire: No checkout credentials, and saved-login fallback is disabled'
      echo 'Entire: ENTIRE_GIT_NO_LOGIN_FALLBACK=true forbids a saved Entire login, and no ENTIRE_TOKEN is available.'
      entire_reason_guidance
      echo 'Entire:   - Or export ENTIRE_TOKEN in an agent environment hook.' ;;
    missing:*)
      echo '+++ :warning: Entire: Checkout had no Entire credentials'
      echo 'Entire: No ENTIRE_TOKEN was set and this agent has no saved Entire login.'
      entire_reason_guidance
      echo 'Entire:   - Or export ENTIRE_TOKEN in an agent environment hook, or run `entire login` on the agent.' ;;
    rejected:supplied)
      echo '+++ :warning: Entire: Entire rejected the supplied ENTIRE_TOKEN'
      echo 'Entire: ENTIRE_TOKEN was already set when the job started, so the plugin did not request credentials from Buildkite.'
      echo 'Entire:   - Check that the token is current and valid for this repository.'
      echo "Entire:   - Or stop setting ENTIRE_TOKEN so Buildkite can issue credentials. Self-hosted agents need \"Allow self-hosted agents to use checkout credentials\": $(entire_settings_url)" ;;
    rejected:issued)
      echo '+++ :warning: Entire: Entire rejected the credentials Buildkite issued'
      echo 'Entire:   - Retry the job. If it keeps failing, contact Buildkite support.' ;;
    rejected:job)
      echo '+++ :warning: Entire: Entire rejected the ENTIRE_TOKEN set during this job'
      echo 'Entire:   - Check where the job sets ENTIRE_TOKEN; the token must be current and valid for this repository.' ;;
    rejected:none)
      echo "+++ :warning: Entire: Entire rejected this agent's saved login"
      echo 'Entire: No ENTIRE_TOKEN was set, so the helper used the saved Entire login on this agent.'
      echo 'Entire:   - Run `entire login` on the agent again.'
      entire_reason_guidance ;;
    other:*)
      echo 'Entire: The Entire helper failed (see its error above). This does not look like an authentication failure.' ;;
  esac
}
