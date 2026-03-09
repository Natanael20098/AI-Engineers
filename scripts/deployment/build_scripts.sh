#!/usr/bin/env bash
# Build, push, and deploy scripts for Natanael microservices
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PROJECT_NAME="natanael"

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
log()   { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] INFO  $*"; }
error() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ERROR $*" >&2; }
die()   { error "$*"; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

# ──────────────────────────────────────────────────────────────
# Build Docker image
# Usage: build <service> <tag>
# ──────────────────────────────────────────────────────────────
cmd_build() {
    local service="${1:?Service name required}"
    local tag="${2:?Image tag required}"
    local service_dir="${PROJECT_ROOT}/services/${service//-/_}"

    require_cmd docker

    [[ -d "${service_dir}" ]] || die "Service directory not found: ${service_dir}"
    [[ -f "${service_dir}/Dockerfile" ]] || die "Dockerfile not found in: ${service_dir}"

    log "Building Docker image for service '${service}' with tag '${tag}'"
    docker build \
        --tag "${PROJECT_NAME}/${service}:${tag}" \
        --tag "${PROJECT_NAME}/${service}:latest" \
        --label "build.commit=$(git -C "${PROJECT_ROOT}" rev-parse --short HEAD)" \
        --label "build.timestamp=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
        --file "${service_dir}/Dockerfile" \
        "${service_dir}"

    log "Build complete: ${PROJECT_NAME}/${service}:${tag}"
}

# ──────────────────────────────────────────────────────────────
# Push Docker image to ECR
# Usage: push <service> <tag> <ecr_registry>
# ──────────────────────────────────────────────────────────────
cmd_push() {
    local service="${1:?Service name required}"
    local tag="${2:?Image tag required}"
    local ecr_registry="${3:?ECR registry URI required}"

    require_cmd docker
    require_cmd aws

    local local_image="${PROJECT_NAME}/${service}:${tag}"
    local remote_image="${ecr_registry}/${PROJECT_NAME}/${service}:${tag}"
    local remote_latest="${ecr_registry}/${PROJECT_NAME}/${service}:latest"

    # Ensure the ECR repository exists
    aws ecr describe-repositories \
        --repository-names "${PROJECT_NAME}/${service}" >/dev/null 2>&1 \
    || aws ecr create-repository \
        --repository-name "${PROJECT_NAME}/${service}" \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256

    log "Tagging image for ECR: ${remote_image}"
    docker tag "${local_image}" "${remote_image}"
    docker tag "${local_image}" "${remote_latest}"

    log "Pushing image to ECR"
    docker push "${remote_image}"
    docker push "${remote_latest}"

    log "Push complete: ${remote_image}"
}

# ──────────────────────────────────────────────────────────────
# Deploy to ECS
# Usage: deploy <service> <tag> <environment> <ecr_registry>
# ──────────────────────────────────────────────────────────────
cmd_deploy() {
    local service="${1:?Service name required}"
    local tag="${2:?Image tag required}"
    local environment="${3:?Environment required}"
    local ecr_registry="${4:?ECR registry URI required}"

    require_cmd aws

    local cluster="${PROJECT_NAME}-${environment}"
    local ecs_service="${PROJECT_NAME}-${environment}-${service}"
    local task_family="${PROJECT_NAME}-${environment}-${service}"
    local image_uri="${ecr_registry}/${PROJECT_NAME}/${service}:${tag}"

    log "Deploying '${service}:${tag}' to ECS cluster '${cluster}' (env: ${environment})"

    # Get current task definition
    local task_def
    task_def=$(aws ecs describe-task-definition \
        --task-definition "${task_family}" \
        --query 'taskDefinition' \
        --output json)

    # Update the image in the container definition
    local new_task_def
    new_task_def=$(echo "${task_def}" | python3 -c "
import json, sys
td = json.load(sys.stdin)
for cd in td['containerDefinitions']:
    if cd['name'] == '${service}':
        cd['image'] = '${image_uri}'
        break
keys_to_remove = ['taskDefinitionArn', 'revision', 'status', 'requiresAttributes',
                  'placementConstraints', 'compatibilities', 'registeredAt', 'registeredBy']
for k in keys_to_remove:
    td.pop(k, None)
print(json.dumps(td))
")

    # Register the new task definition revision
    local new_revision
    new_revision=$(aws ecs register-task-definition \
        --cli-input-json "${new_task_def}" \
        --query 'taskDefinition.taskDefinitionArn' \
        --output text)

    log "Registered new task definition revision: ${new_revision}"

    # Update the ECS service to use the new task definition
    aws ecs update-service \
        --cluster "${cluster}" \
        --service "${ecs_service}" \
        --task-definition "${new_revision}" \
        --force-new-deployment

    log "Waiting for ECS service to stabilize..."
    aws ecs wait services-stable \
        --cluster "${cluster}" \
        --services "${ecs_service}"

    log "Deployment complete: ${service} @ ${environment}"
}

# ──────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────
main() {
    local command="${1:-}"
    shift || true

    case "${command}" in
        build)  cmd_build  "$@" ;;
        push)   cmd_push   "$@" ;;
        deploy) cmd_deploy "$@" ;;
        *)
            echo "Usage: $0 {build|push|deploy} [args...]"
            echo ""
            echo "Commands:"
            echo "  build  <service> <tag>                             Build Docker image"
            echo "  push   <service> <tag> <ecr_registry>              Push image to ECR"
            echo "  deploy <service> <tag> <environment> <ecr_registry> Deploy to ECS"
            exit 1
            ;;
    esac
}

main "$@"
